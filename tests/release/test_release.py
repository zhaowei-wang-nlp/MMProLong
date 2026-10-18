"""Portable checks for the public entry points; no model downloads or accelerators."""

import argparse
import ast
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def dataclass_fields(path, name):
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == name)
    return {node.target.id for node in cls.body if isinstance(node, ast.AnnAssign)}


class ReleaseConfigTests(unittest.TestCase):
    def test_training_entries_match_argument_schema_and_reference_real_files(self):
        base = ROOT / "veomni/arguments/arguments_types.py"
        task = ROOT / "tasks/omni/train_qwen_vl.py"
        fields = {
            "model": dataclass_fields(base, "ModelArguments"),
            "data": dataclass_fields(base, "DataArguments") | dataclass_fields(task, "MyDataArguments"),
            "train": dataclass_fields(base, "TrainingArguments") | dataclass_fields(task, "MyTrainingArguments"),
        }
        for path in (ROOT / "configs/mmprolong").glob("*.yaml"):
            with self.subTest(config=path.name):
                config = yaml.safe_load(path.read_text())
                self.assertEqual(set(config), set(fields))
                for section, allowed in fields.items():
                    self.assertFalse(set(config[section]) - allowed, f"Unknown {section} fields")
                self.assertTrue((ROOT / config["data"]["train_path"]).is_file())
                model_path = config["model"].get("config_path")
                if model_path:
                    self.assertTrue((ROOT / model_path).is_file())
                    json.loads((ROOT / model_path).read_text())

    def test_mixture_probabilities_and_source_counts(self):
        for folder in ("qwen_vl_mix_yaml", "qwen_vl_short_mix_yaml"):
            for path in (ROOT / "scripts" / folder).glob("*.yaml"):
                with self.subTest(mixture=path.name):
                    config = yaml.safe_load(path.read_text())
                    count = len(config["sources"])
                    self.assertEqual(count, len(set(config["names"])))
                    for stage in config["schedule"]:
                        self.assertEqual(len(stage["weights"]), count)
                        self.assertTrue(all(weight >= 0 for weight in stage["weights"]))
                        self.assertAlmostEqual(sum(stage["weights"]), 1.0, places=4)
                        if "token_weights" in stage:
                            self.assertEqual(len(stage["token_weights"]), count)
                            self.assertEqual(len(stage["avg_len"]), count)
                            self.assertTrue(all(length > 0 for length in stage["avg_len"]))
                            self.assertAlmostEqual(sum(stage["token_weights"]), 1.0)
                            # The loader reads sample weights; recover their expected token shares.
                            token_mass = [
                                weight * length for weight, length in zip(stage["weights"], stage["avg_len"])
                            ]
                            total = sum(token_mass)
                            for mass, expected in zip(token_mass, stage["token_weights"]):
                                self.assertAlmostEqual(mass / total, expected, places=7)

                            short_fraction = int(path.stem.rsplit("short", 1)[1]) / 100
                            self.assertAlmostEqual(stage["token_weights"][-1], short_fraction)
                            if short_fraction < 1:
                                extraction, reasoning = map(int, path.stem.split("_")[3:5])
                                long_mass = sum(token_mass[:-1])
                                self.assertAlmostEqual(
                                    sum(token_mass[:2]) / long_mass,
                                    extraction / (extraction + reasoning),
                                    places=7,
                                )


class LauncherTests(unittest.TestCase):
    def run_launcher(self, extra_env=None, args=None, wrapper=None):
        with tempfile.TemporaryDirectory(prefix="mmprolong launcher ") as directory:
            temporary = Path(directory)
            captured = temporary / "args.json"
            mock = temporary / "torchrun"
            mock.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, sys\n"
                "open(os.environ['CAPTURE_ARGS'], 'w').write(json.dumps(sys.argv[1:]))\n"
                "sys.exit(int(os.environ.get('MOCK_EXIT', '0')))\n"
            )
            mock.chmod(0o755)
            env = dict(os.environ)
            for name in ("NNODES", "NODE_RANK", "MASTER_ADDR", "MASTER_PORT", "NPROC_PER_NODE"):
                env.pop(name, None)
            env.update(
                PATH=f"{temporary}{os.pathsep}{env['PATH']}",
                NPROC_PER_NODE="8",
                CAPTURE_ARGS=str(captured),
                LOG_FILE=str(temporary / "train log.txt"),
            )
            env.update(extra_env or {})
            launcher = ROOT / (wrapper or "train.sh")
            if args is None:
                args = ["task.py", "config.yaml", "--train.output_dir", "/path with spaces/output"]
            result = subprocess.run(
                ["bash", str(launcher), *args], cwd=temporary, env=env, capture_output=True, text=True
            )
            received = json.loads(captured.read_text()) if captured.exists() else []
            return result, received

    def test_single_node_and_quoted_overrides(self):
        result, args = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--standalone", args)
        self.assertEqual(args[-1], "/path with spaces/output")

    def test_multi_node_preserves_rank_and_rendezvous(self):
        result, args = self.run_launcher(
            {"NNODES": "8", "NODE_RANK": "3", "MASTER_ADDR": "training-head", "MASTER_PORT": "29601"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for key, expected in (
            ("--nnodes", "8"),
            ("--node-rank", "3"),
            ("--master-addr", "training-head"),
            ("--master-port", "29601"),
        ):
            self.assertEqual(args[args.index(key) + 1], expected)
        self.assertNotIn("--standalone", args)

    def test_training_failure_is_not_hidden_by_tee(self):
        result, _ = self.run_launcher({"MOCK_EXIT": "7"})
        self.assertEqual(result.returncode, 7)

    def test_multi_node_requires_master_address(self):
        result, args = self.run_launcher({"NNODES": "2"})
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(args)

    def test_wrapper_selects_recipe_and_keeps_overrides(self):
        for name in ("qwen25_vl_7b", "qwen3_vl_8b"):
            result, args = self.run_launcher(
                args=["--data.train_path", "/path with spaces/mixture.yaml"],
                wrapper=f"scripts/qwen_vl_job/run_{name}_vqa.sh",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"configs/mmprolong/{name}_128k.yaml", args)
            self.assertEqual(args[-1], "/path with spaces/mixture.yaml")

    def test_qwen25_wrapper_passes_original_128k_config(self):
        result, args = self.run_launcher(args=[], wrapper="scripts/qwen_vl_job/run_qwen25_vl_7b_vqa.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--model.config_path", dest="config_path")
        selected, _ = parser.parse_known_args(args)
        self.assertEqual(selected.config_path, "configs/model_configs/qwen/mmprolong_qwen25_vl_7b_128k.json")
        config = json.loads((ROOT / selected.config_path).read_text())
        self.assertEqual(config["rope_theta"], 4_000_000)
        self.assertEqual(config["max_position_embeddings"], 131_072)

    def test_qwen25_3b_override_replaces_7b_config(self):
        model = "Qwen/Qwen2.5-VL-3B-Instruct"
        config_path = "configs/model_configs/qwen/mmprolong_qwen25_vl_3b_128k.json"
        result, args = self.run_launcher(
            args=["--model.model_path", model, "--model.tokenizer_path", model, "--model.config_path", config_path],
            wrapper="scripts/qwen_vl_job/run_qwen25_vl_7b_vqa.sh",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--model.model_path", dest="model_path")
        parser.add_argument("--model.tokenizer_path", dest="tokenizer_path")
        parser.add_argument("--model.config_path", dest="config_path")
        selected, _ = parser.parse_known_args(args)
        self.assertEqual(selected.model_path, model)
        self.assertEqual(selected.tokenizer_path, model)
        self.assertEqual(selected.config_path, config_path)
        config = json.loads((ROOT / selected.config_path).read_text())
        self.assertEqual(config["hidden_size"], 2048)
        self.assertEqual(config["rope_theta"], 4_000_000)
        self.assertEqual(config["max_position_embeddings"], 131_072)


if __name__ == "__main__":
    unittest.main()

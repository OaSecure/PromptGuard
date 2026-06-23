# PromptGuard Model Artifacts

PromptGuard loads ML artifacts from a Docker-mounted model directory.

Recommended local layout:

```text
promptguard_publish/
  models/
    context_lr_roberta_active_best_f1_manifest.json
    context_with_patch_v287_lr_c4_dev_classifier.joblib
    context_target_labels.json
    context_label_definitions_verifier_compact_v2.json
    context_verifier_klue_roberta_base_lrmined_v287_global002_compactv2_lpft_focal_1p2ep/
      config.json
      model.safetensors
      tokenizer.json
      tokenizer_config.json
      special_tokens_map.json
```

Recommended container layout:

```text
/opt/promptguard/models/
  context_lr_roberta_active_best_f1_manifest.json
  context_with_patch_v287_lr_c4_dev_classifier.joblib
  context_target_labels.json
  context_label_definitions_verifier_compact_v2.json
  context_verifier_klue_roberta_base_lrmined_v287_global002_compactv2_lpft_focal_1p2ep/
```

`compose.yml` mounts `./models` into the API container as read-only:

```text
./models:/opt/promptguard/models:ro
```

Download the current artifact bundle from Hugging Face Hub from the repository
root:

```bash
pip install "huggingface_hub[hf_xet]"
huggingface-cli download OASecure/promptguard-context-classifier \
  --revision v287-20260623 \
  --include "models/*" \
  --local-dir .
```

Configure runtime loading with absolute container paths:

```env
PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json

PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_roberta_active_best_f1_manifest.json
```

The v287 classifier and verifier share one manifest. The classifier loader uses
the LR model, target labels, and `lr_candidate_policy.candidate_threshold`. The
verifier loader uses the verifier directory, label definitions, label-wise
thresholds, max token length, and chunk policy from the same manifest.

If you keep the exported zip layout exactly as delivered, point both manifest
environment variables to the manifest under the export's `models/` directory.
For a cleaned deployment layout, place the manifest and the two context JSON
files directly under the mounted model directory as shown above.

The files under `models/examples/` are documentation samples only. Do not use
them as trained artifacts.

Do not commit real model artifacts to Git:

- `*.joblib`
- `*.pkl`
- `*.pt`
- `*.bin`
- `*.safetensors`
- HuggingFace model directories

Keep real artifacts in the local `models/` directory, mounted into Docker, or
provided by the deployment environment.

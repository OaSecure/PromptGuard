# PromptGuard Model Artifacts

PromptGuard loads ML artifacts from a Docker-mounted model directory.

Recommended local layout:

```text
promptguard_publish/
  models/
    context_lr_manifest.json
    context_with_patch_v205_deploy_candidate_classifier.joblib
    context_target_labels.json
    context_roberta_verifier_manifest.json
    context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6/
      config.json
      model.safetensors
      tokenizer.json
      tokenizer_config.json
      special_tokens_map.json
```

Recommended container layout:

```text
/opt/promptguard/models/
  context_lr_manifest.json
  context_with_patch_v205_deploy_candidate_classifier.joblib
  context_target_labels.json
  context_roberta_verifier_manifest.json
  context_verifier_klue_roberta_base_patch_v204_all_from_v177_1ep_lr1e6/
```

`compose.yml` mounts `./models` into the API container as read-only:

```text
./models:/opt/promptguard/models:ro
```

Configure runtime loading with absolute container paths:

```env
PROMPTGUARD_CLASSIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_CLASSIFIER_MANIFEST_PATH=/opt/promptguard/models/context_lr_manifest.json

PROMPTGUARD_VERIFIER_RUNTIME_ENABLED=true
PROMPTGUARD_VERIFIER_MANIFEST_PATH=/opt/promptguard/models/context_roberta_verifier_manifest.json
```

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

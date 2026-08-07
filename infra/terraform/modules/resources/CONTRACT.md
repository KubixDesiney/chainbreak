# Module contract: `resources`

The benign resources probes act on, plus the markers that make probe results
interpretable. Implementation is milestone M9.

## Required inputs

`namespace`, `marker_payload` (JSON string, defaults to a fixed document), `scratch_expiry_days`
(default `1`), `log_retention_days` (default `1`).

## Required outputs

`objectstore_bucket`, `objectstore_marker_key`, `objectstore_marker_sha256`,
`keyvalue_table`, `keyvalue_marker_pk`, `keyvalue_marker_sha256`, `function_name`,
`function_arn`, `queue_url`, `queue_arn`, and the ARN set consumed by `identities`.

## Resources

| Resource | Requirements |
|---|---|
| `aws_s3_bucket` `cb-{ns}-objectstore` | `force_destroy = true`; public access fully blocked; SSE enabled; lifecycle rule expiring `cb-{ns}/scratch/` after `scratch_expiry_days` |
| `aws_s3_object` marker | Key `cb-{ns}/markers/marker.json`; content from `marker_payload`; its SHA-256 is an output |
| `aws_dynamodb_table` `cb-{ns}-keyvalue` | **`PAY_PER_REQUEST` billing** — provisioned capacity is the single most likely way to accidentally spend money here; `ttl` attribute enabled |
| `aws_dynamodb_table_item` marker | `pk = "cb-marker"`; digest is an output |
| `aws_lambda_function` `cb-{ns}-noop` | `python3.12`, 128 MB, 3 s timeout, no VPC, no layers; returns `{"ok": true, "nonce": <namespace>}` |
| `aws_cloudwatch_log_group` | `/aws/lambda/cb-{ns}-noop`, retention `log_retention_days`, **managed explicitly** so Lambda's implicit group cannot orphan |
| `aws_sqs_queue` `cb-{ns}-queue` | Standard; `visibility_timeout_seconds = 0` so receive probes are effectively non-destructive |

## The marker digests are load-bearing

`objectstore_marker_sha256` and `keyvalue_marker_sha256` are not conveniences. A read probe
counts as `ALLOWED` **only** if the returned content matches the expected digest — "no
exception raised" is not success. On S3 a `GetObject` against a missing key returns
`AccessDenied` rather than `NoSuchKey` when the caller lacks `s3:ListBucket`, so without a
verified marker a missing object is indistinguishable from a denial and `objectstore.read`
cannot be measured at all. See
[AWS_PROVIDER_SPEC §6.1](../../../../AWS_PROVIDER_SPEC.md#61-the-403404-problem).

## Object and item layout

```
cb-{ns}/markers/marker.json            # read probes; created at apply time
cb-{ns}/scratch/{run_id}/{probe_id}    # write probes; run-scoped, lifecycle-expired
```

DynamoDB: `pk = "cb-marker"` for reads; `pk = "cb-scratch#{run_id}#{probe_id}"` with a `ttl`
for writes. Run-scoping is what structurally prevents cross-run contamination (T-08) — it is
a property of the key layout, not of operator discipline.

## Verification

```
terraform apply && terraform destroy && terraform destroy   # second destroy is a no-op
aws s3api head-object --bucket $(terraform output -raw objectstore_bucket) \
  --key $(terraform output -raw objectstore_marker_key)
```

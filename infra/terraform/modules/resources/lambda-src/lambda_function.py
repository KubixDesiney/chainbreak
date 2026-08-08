# The benchmark no-op function. Performs no work and returns a fixed payload
# containing a nonce -- capabilities/catalog.yaml's own function.invoke
# description. The nonce is the deploying namespace, baked in at apply time
# via NAMESPACE, never derived from the caller's input: there is nothing
# per-call to echo (AWS_PROVIDER_SPEC section 6.2).

import os


def handler(event, context):
    return {"ok": True, "nonce": os.environ["NAMESPACE"]}

# Module: Runtime

MissionForge runtime code is deliberately small:

- build or receive a `PiWorkerCall`;
- enforce workspace and permission boundaries;
- invoke the Pi sidecar adapter;
- normalize the result into `PiWorkerCallResult`;
- record refs-first evidence, metrics, and progress.

Runtime code does not decide product-level semantic acceptance. That belongs
to a separate judge PiWorker or product integration.

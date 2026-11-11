def normalise_device_name(name: str | None) -> str | None:
    """Case-fold a device name; ``None`` passes through.

    Device names are stored lower-cased so that a device registered as "MAST"
    resolves through ``/devices/mast`` and vice versa. Apply this to every
    externally supplied device name, on both write and lookup paths; use
    ``title`` for the canonical display form.
    """
    return name.lower() if name is not None else None

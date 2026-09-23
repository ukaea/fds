DEVICE = "/devices/{name}"
SHOT = "/devices/{name}/shots/{shot_id}"
DATASET = "/datasets/{id}"
COLLECTION = "/collections/{id}"
SOURCE = "/sources/{id}"
ACTIVITY = "/activities/{id}"


class Identifiers:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")

    def device(self, name: str) -> str:
        return self.base + DEVICE.format(name=name)

    def shot(self, device_name: str, shot_id: object) -> str:
        return self.base + SHOT.format(name=device_name, shot_id=shot_id)

    def dataset(self, id: object) -> str:
        return self.base + DATASET.format(id=id)

    def collection(self, id: object) -> str:
        return self.base + COLLECTION.format(id=id)

    def source(self, id: object) -> str:
        return self.base + SOURCE.format(id=id)

    def activity(self, id: object) -> str:
        return self.base + ACTIVITY.format(id=id)


def resolve_base(configured: str, request_origin: str) -> str:
    return configured.strip().rstrip("/") or request_origin.rstrip("/")

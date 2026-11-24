"""The same in every recording, so that no setting says what will go wrong."""

# The claim is longer than any transaction may take, as it is in production. One worker does one thing at a time, so nobody else goes
# down with it.
SETTINGS = {"PLATFORM_LEASE_MS": "12000", "PLATFORM_PAUSE_MS": "100", "PLATFORM_FIRST_DELAY_MS": "1000", "PLATFORM_TROUBLE_DELAY_MS": "1000", "PLATFORM_LOOPS": "1"}
LEASE = int(SETTINGS["PLATFORM_LEASE_MS"]) / 1000
FEEDS = (("north-web", "north"), ("north-app", "north"), ("south-web", "south"), ("south-app", "south"))
ITEMS = ("BOX-S", "BOX-M", "MUG-1", "MUG-2", "TEE-S", "TEE-L")
# The largest body that the platform takes.
BODY = 256 * 1024

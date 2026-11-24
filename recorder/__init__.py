"""Makes the recordings: it runs webhook-platform as it really is, lets one thing go wrong, and writes down what can be seen.

It needs Docker, .NET and the commit of webhook-platform that stands in webhook-platform.commit. It knows what went wrong. Nothing of
that comes into a recording, and the truth goes into another folder.
"""

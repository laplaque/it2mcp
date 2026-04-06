"""Custom redaction plugins directory.

Drop .py files here (or in ~/.config/it2mcp/redact-plugins/) to add
custom secret redaction patterns. Each file should contain one or more
classes that subclass it2mcp.redact.base.RedactPlugin.

Example custom plugin:

    import re
    from it2mcp.redact.base import RedactPlugin

    class MyCompanyPlugin(RedactPlugin):
        @property
        def name(self) -> str:
            return "mycompany"

        @property
        def description(self) -> str:
            return "My company's internal API keys"

        def patterns(self) -> list[re.Pattern[str]]:
            return [
                re.compile(r"myco_[A-Za-z0-9]{32}"),
            ]
"""

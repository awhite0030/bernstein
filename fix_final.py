with open("scripts/quorum_check.py", "r") as f:
    content = f.read()

old_stops = 'if pr.author in roster.automation or pr.author == "google-labs-jules[bot]":'
new_stops = 'if pr.author in roster.automation or pr.author in ("google-labs-jules[bot]", "jules"):'
if old_stops in content:
    content = content.replace(old_stops, new_stops)

old_auth = 'elif pr.author in (GITHUB_ACTIONS_BOT, "google-labs-jules[bot]"):'
new_auth = 'elif pr.author in (GITHUB_ACTIONS_BOT, "google-labs-jules[bot]", "jules"):'
if old_auth in content:
    content = content.replace(old_auth, new_auth)

with open("scripts/quorum_check.py", "w") as f:
    f.write(content)

with open(".github/quorum-roster.toml", "r") as f:
    content = f.read()

old_auto = 'automation = ["bernstein-the-conductor[bot]", "renovate[bot]", "dependabot[bot]", "google-labs-jules[bot]"]'
new_auto = 'automation = ["bernstein-the-conductor[bot]", "renovate[bot]", "dependabot[bot]", "google-labs-jules[bot]", "jules"]'
if old_auto in content:
    content = content.replace(old_auto, new_auto)

with open(".github/quorum-roster.toml", "w") as f:
    f.write(content)

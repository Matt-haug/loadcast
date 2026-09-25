# Contributing

Contributions are welcome — issues, questions and pull requests alike.

## Support and scope

**Maintenance.** `loadcast` is maintained by one person alongside doctoral
research. Issues are usually answered within a week or two; there is no
service-level guarantee, and quiet periods around deadlines are normal. If
something is urgent, say so in the issue and it will be triaged sooner.

**Decisions.** The maintainer makes the final call on scope and design. The
reasoning behind a decision is written down in the issue rather than left
implicit, so a disagreement is about something readable.

**What belongs here.** The package generates demand *quantities* for industrial
carriers, with the coincidence between them as an explicit input. Three things
are deliberately out of scope, and a pull request adding them will be declined
with this paragraph rather than silence:

- **Temperature.** `loadcast` carries energy by carrier. Whether a machine can
  reach a process is answered from the machine's own limits, not from here.
  `loadcast.reference` reports published temperatures as information only.
- **Any specific technology.** No heat pumps, no storage models, no dispatch.
  The generator produces demand; what you do with it is your study.
- **A default that is really an assumption.** Every parameter stays the user's
  to choose. Indicative values ship with their provenance and their caveat, and
  never silently become defaults.

## Reporting something

Open an issue with the version (`loadcast.__version__`), the spec that produced
the behaviour, and what you expected instead. A five-line reproduction is worth
more than a description.

Reports that the generated profiles disagree with a real site you have measured
are **especially welcome** — the calibration archive is small (two branches,
five series), and its narrowness is the package's main limitation.

## Making a change

```bash
git clone https://github.com/Matt-haug/loadcast
cd loadcast
python -m pip install -e ".[dev]"
python -m pytest
```

Then:

1. Open an issue first for anything beyond a fix, so the design can be agreed
   before you spend time on it.
2. Keep the change focused. One concern per pull request.
3. Add a test. See below for what that means here.
4. Update `CHANGELOG.md` under `[Unreleased]`.

### Tests here are mostly identities

The generator makes exact promises — annual energy, the carrier ratio, the
electricity share, the load factor — so most tests assert an identity rather
than a stored fixture. `tests/test_identities.py` is the model: each test
corresponds to one derivation in `docs/mathematics.md`.

If you change the mathematics, change `docs/mathematics.md` in the same pull
request. The documentation is the specification; the tests check it.

A statistic that is *aimed at* rather than imposed (spread, persistence) is
tested against a tolerance, and the systematic offset is pinned in
`test_imposed_statistics_are_exact_and_emergent_ones_are_not` so it cannot widen
unnoticed.

### Style

Follow what is there: explanatory docstrings that say *why* a step exists and
what goes wrong without it, comments only where the reason is not evident from
the code, and no abbreviation of names that a reader would have to decode.

## Calibration data

The metered series behind the process classes cannot be redistributed. What
ships is derived statistics and calendar factors — group means carrying no
identifying information. **Do not add raw site data to this repository.**

New process classes calibrated on data you can share are very welcome; open an
issue describing the site and its statistics first.

## Using generative AI

Permitted, and it must be disclosed in the pull request: which tool, what it was
used for, and confirmation that you reviewed and validated the result and made
the design decisions yourself. See `AI_USAGE.md` for the project's own
disclosure and the level of detail expected.

A contribution you have not read and understood is not a contribution; it is a
review burden transferred to someone else.

"""A filter of canonical N-Quads (stdin to stdout) applied before the fingerprint of the
outputs of the workloads that ask for it (GTFS France: real data, whose identifiers have
non-ASCII characters and whose numbers are written in several ways). It removes two
differences between outputs that RML-Core allows or recommends, and no other:

- in an IRI, a sequence of percent-encoded octets that is the UTF-8 encoding of a non-ASCII
  character is replaced by that character: RML-Core builds an IRI from a template with the
  IRI-safe version of each value, which keeps such characters ("Zoë Krüger" gives
  "Zoë%20Krüger", RML-Core, IRI encoding); an engine that writes their URI-safe version
  ("Zo%C3%AB%20Kr%C3%BCger") gives the same IRI after this filter. An encoded ASCII
  character (%3A) is kept: a ':' written as is gives another IRI;
- the lexical form of an xsd:double literal is replaced by its canonical form ("0.000" and
  "0.0E0" give "0.0E0"): RML-Core's datatype-override literal has the natural RDF lexical
  form, on which implementations SHOULD apply the XSD canonical mapping.

Usage: ... | python3 -I harness/ntnormalise.py | ...
"""
import decimal
import re
import sys

IRI = re.compile(r"<[^<>\s]*>")
UTF8 = re.compile(r"(?:%[C-Fc-f][0-9A-Fa-f](?:%[89ABab][0-9A-Fa-f])+)")
DOUBLE = re.compile(r'"([^"\\]*)"\^\^<http://www\.w3\.org/2001/XMLSchema#double>')
DT = "^^<http://www.w3.org/2001/XMLSchema#double>"


def _decode(m):
    s = m.group(0)
    try:
        text = bytes(int(h, 16) for h in s[1:].split("%")).decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return s
    # only characters that the IRI-safe version keeps (ucschar: not ASCII, not a surrogate)
    return text if all(ord(c) > 0x7F for c in text) else s


def iri(m):
    t = m.group(0)
    return UTF8.sub(_decode, t) if "%" in t else t


def canonical_double(lex):
    """The XSD 1.1 canonical form of a double: INF, -INF, NaN, or a mantissa of one
    non-zero digit before the point (at least one after) and an exponent: 1.5E1, 0.0E0."""
    s = lex.strip()
    if s in ("INF", "+INF", "-INF", "NaN"):
        return s.lstrip("+")
    try:
        f = float(s)
    except ValueError:
        return lex
    if f != f:
        return "NaN"
    if f in (float("inf"), float("-inf")):
        return "INF" if f > 0 else "-INF"
    if f == 0:
        return "-0.0E0" if str(f).startswith("-") else "0.0E0"
    sign, digits, exp = decimal.Decimal(repr(f)).as_tuple()
    digits = "".join(map(str, digits)).rstrip("0") or "0"
    e = exp + len("".join(map(str, decimal.Decimal(repr(f)).as_tuple()[1]))) - 1
    return "%s%s.%sE%d" % ("-" if sign else "", digits[0], digits[1:] or "0", e)


def line(text):
    if "%" in text:
        text = IRI.sub(iri, text)
    if DT in text:
        text = DOUBLE.sub(lambda m: '"%s"%s' % (canonical_double(m.group(1)), DT), text)
    return text


def main():
    out = sys.stdout
    for l in sys.stdin:
        out.write(line(l))


if __name__ == "__main__":
    main()

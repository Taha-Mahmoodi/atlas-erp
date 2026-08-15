"""Adversarial review of the machine-credential key STRING (spec Q1, Phase 18).

`core/auth.parse_api_key` is the first code an unauthenticated attacker reaches:
`get_current_user` calls it on the raw Authorization credentials before any signature
check, any database read, and before the D-007 tenancy ContextVar is set. Three properties
have to hold for every byte string a client can put in that header.

1. **It is a total function.** It must return None, never raise — deps.py turns None into
   an opaque 401, while an exception there is a 500 with a stack trace on an
   unauthenticated endpoint.
2. **No segment is lost or mis-attributed.** The key is `scheme_ref_secret` joined by a
   character the segments themselves may contain. A split that lands in the wrong place
   either truncates the secret (a credential that is dead the moment it is issued, with no
   error saying why) or mangles the ref (which is what the tenancy ContextVar is set from).
3. **Only the digest decides.** The ref is attacker-controlled by construction, so
   authenticating must come down to an equality match on a stored sha256 and nothing else.

These tests deliberately obtain their key from the REAL issuing endpoint
(`POST /api/v1/admin/api-keys`) and mutate what it returns, rather than assembling a key
string from assumed parts. That keeps the file honest across a change to the key format:
it asserts the round-trip and the rejections, never the internal shape.
"""

import inspect
import random
import string
import uuid
from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

import app.core.auth as auth_module
from app.core.auth import encode_access, mint_api_key, parse_api_key, sha256_hex
from app.core.rbac import ADMIN_USER_MANAGE
from tests.conftest import ProvisionedUser, QueryCounter

_KEYS = "/api/v1/admin/api-keys"
_GUARDED = "/api/v1/admin/users"


def _bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


IssuedKey = Callable[[], Awaitable[str]]


@pytest.fixture
def issue_key(admin_client: AsyncClient, admin_user: ProvisionedUser) -> IssuedKey:
    """A key from the real issuer, exactly as an operator would receive it. Nothing here
    knows how the string is put together — that is the point."""

    async def _issue() -> str:
        response = await admin_client.post(
            _KEYS,
            json={
                "name": "website",
                "user_id": str(admin_user.user_id),
                "scopes": [ADMIN_USER_MANAGE],
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["key"]

    return _issue


# --- 1. The parser is total ---------------------------------------------------

# Every shape the review brief names, plus the ones a header can actually carry.
_HOSTILE = [
    "",
    "_",
    "__",
    "___",
    "atk",
    "atk_",
    "atk__",
    "atk__x",  # empty ref
    "atk_x_",  # empty secret
    "atk_x",  # no secret segment at all
    "_atk_x",  # empty scheme
    "atk_acme_secret",  # a slug-shaped ref: the format this branch started with
    "atk_acme_corp_secret",  # ...and one carrying the delimiter itself
    "ATK_acme_secret",  # the scheme is case sensitive
    "atk _acme_secret",
    " atk_acme_secret",  # a second space after "Bearer"
    "atk_acme_secret ",
    "\tatk_acme_secret",
    "Bearer atk_acme_secret",  # the auth scheme left attached
    "bearer atk_acme_secret",
    "notakey",
    "not_a_key",
    "sk_live_abcdef",  # a plausible foreign credential
    "atk-acme-secret",  # right shape, wrong delimiter
    "atk.acme.secret",
    "é_é_é",
    "atk_ünïcode_secret",
    "atk_acme_ünïcode",
    "atk_\U0001f511_secret",  # non-BMP
    "atk_acme_secret\n",
    "atk_acme_sec\x00ret",
    "atk_\x00_x",
    "%_%_%",
    "atk_%_%",  # SQL wildcards where the ref goes
    "atk_' OR 1=1 --_x",
    "atk_" + "١" * 32 + "_x",  # non-ASCII digits: int(base=16) accepts them
    "atk_{" + "0" * 32 + "}_x",
    "atk_" + "0" * 32 + "_" + "x" * 100_000,  # unbounded secret
    "atk_" + "y" * 100_000 + "_secret",  # unbounded ref
    "x" * 500_000,  # no delimiter at all, very long
]


@pytest.mark.parametrize("raw", _HOSTILE, ids=range(len(_HOSTILE)))
def test_parse_never_raises_on_hostile_input(raw: str) -> None:
    """Total function: a result or None, never an exception."""
    result = parse_api_key(raw)

    assert result is None or (isinstance(result, tuple) and len(result) == 2)


def test_parse_never_raises_under_fuzz() -> None:
    """The curated list above only covers what a reviewer thought of. Fuzz the alphabet
    that actually matters — the delimiter, everything `uuid.UUID(hex=...)` strips or
    tolerates, and the characters an HTTP header can legally carry."""
    alphabet = list("_-.{}:+ \t0123456789abcdefABCDEFxX%'\"\\/") + [
        "atk",
        "urn:",
        "uuid:",
        "0x",
        "١",
        "é",
        "\U0001f511",
    ]
    rng = random.Random(20260814)
    for _ in range(50_000):
        raw = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 14)))
        try:
            parse_api_key(raw)
        except Exception as exc:  # pragma: no cover - the assertion is the report
            pytest.fail(f"parse_api_key({raw!r}) raised {type(exc).__name__}: {exc}")


@pytest.mark.parametrize(
    "raw", [r for r in _HOSTILE if r.isascii() and r.isprintable()], ids=lambda r: str(len(r))
)
async def test_hostile_credentials_are_401_never_5xx(client: AsyncClient, raw: str) -> None:
    """The same strings over the wire. Whether the parser rejects them or the JWT decode
    does, the answer is an opaque 401 — a 5xx here leaks a stack trace to an
    unauthenticated caller."""
    response = await client.get(_GUARDED, headers=_bearer(raw))

    assert response.status_code == 401, f"{raw[:40]!r} -> {response.status_code}"


async def test_oversized_credential_costs_at_most_one_query(
    client: AsyncClient, query_counter: Callable[[], QueryCounter]
) -> None:
    """A 100 KB bearer value must not become a 100 KB bound parameter on a pre-auth lookup.
    The ref is length-bounded by its own format check, so an oversized credential is thrown
    out before it can reach the database as a parameter."""
    with query_counter() as counter:
        response = await client.get(
            _GUARDED, headers=_bearer("atk_" + "y" * 100_000 + "_secret")
        )

    assert response.status_code == 401
    assert counter.count == 0, (
        f"oversized ref reached the database in {counter.count} quer(ies):\n"
        + "\n".join(counter.statements)
    )


# --- 2. Round-trip: no segment is lost ----------------------------------------


def test_mint_and_parse_round_trip_over_many_refs() -> None:
    """Property, not an example: whatever the issuer mints must parse back to the same ref
    and the same digest. The failure this guards is silent — a truncated secret produces a
    credential that 401s forever with nothing in any log to explain it."""
    for _ in range(500):
        ref = uuid.uuid4()
        full, digest = mint_api_key(ref)

        parsed = parse_api_key(full)

        assert parsed is not None, f"key minted for {ref} does not parse at all"
        assert parsed == (ref, digest), f"key minted for {ref} parsed as {parsed!r}"


def test_the_digest_covers_the_secret_and_nothing_else() -> None:
    """The stored digest must be of the secret alone. If the ref were folded in, rotating a
    tenant's identifier would silently invalidate every key it holds."""
    ref = uuid.uuid4()
    full, digest = mint_api_key(ref)
    secret = full.split("_", 2)[2]

    assert digest == sha256_hex(secret)
    assert secret not in full[: len(full) - len(secret)]


def test_the_key_string_carries_no_tenant_slug() -> None:
    """Regression net for the delimiter collision this branch shipped with.

    The key originally carried the tenant SLUG, and `provision_tenant` (the path seed, the
    test factory and every non-onboarding caller use) applies no slug validation — only the
    onboarding wizard slugifies, and `adm_tenants.slug` is an unconstrained VARCHAR. A slug
    holding the delimiter therefore split the secret in half and produced a dead key. The
    ref is a tenant UUID now; assert that, so a revert to a free-text ref fails here rather
    than in production."""
    full, _ = mint_api_key(uuid.uuid4())
    scheme, ref, secret = full.split("_", 2)

    assert scheme == auth_module.API_KEY_PREFIX
    assert uuid.UUID(hex=ref).hex == ref, f"ref {ref!r} is not canonical UUID hex"
    assert "_" not in ref


# --- 3. Only the digest decides -----------------------------------------------


async def test_an_issued_key_authenticates(client: AsyncClient, issue_key: IssuedKey) -> None:
    """Baseline for every mutation below."""
    response = await client.get(_GUARDED, headers=_bearer(await issue_key()))

    assert response.status_code == 200, response.text


async def test_no_mutation_of_a_real_key_authenticates(
    client: AsyncClient, issue_key: IssuedKey
) -> None:
    """Take a genuine key and damage it every way a client could. None may pass, and none
    may 5xx — including the mutations that keep the ref intact, which is what proves the
    secret is doing the work and not the ref."""
    full = await issue_key()
    scheme, ref, secret = full.split("_", 2)

    mutations = {
        "secret truncated by one": f"{scheme}_{ref}_{secret[:-1]}",
        "secret truncated hard": f"{scheme}_{ref}_{secret[:8]}",
        "secret extended": f"{scheme}_{ref}_{secret}x",
        "secret case-flipped": f"{scheme}_{ref}_{secret.swapcase()}",
        "secret is a wildcard": f"{scheme}_{ref}_%",
        "secret is all wildcards": f"{scheme}_{ref}_{'%' * len(secret)}",
        "secret quoted out": f"{scheme}_{ref}_' OR 1=1 --",
        "secret empty": f"{scheme}_{ref}_",
        "ref empty": f"{scheme}__{secret}",
        "ref forged": f"{scheme}_{uuid.uuid4().hex}_{secret}",
        "ref is a slug": f"{scheme}_acme_{secret}",
        "scheme dropped": f"{ref}_{secret}",
        "scheme uppercased": f"{scheme.upper()}_{ref}_{secret}",
        "scheme misspelled": f"{scheme}x_{ref}_{secret}",
        "delimiter swapped": full.replace("_", "-"),
        "space inside the secret": f"{scheme}_{ref}_{secret[:4]} {secret[4:]}",
        "space inside the ref": f"{scheme}_{ref[:4]} {ref[4:]}_{secret}",
        "bearer re-attached": f"Bearer {full}",
        "reversed": full[::-1],
    }
    for label, forged in mutations.items():
        response = await client.get(_GUARDED, headers=_bearer(forged))
        assert response.status_code == 401, f"{label}: {response.status_code}"


async def test_whitespace_around_the_credential(
    client: AsyncClient, issue_key: IssuedKey
) -> None:
    """SURROUNDING whitespace never reaches `parse_api_key` — FastAPI's
    `get_authorization_scheme_param` partitions on the first space and `.strip()`s the
    parameter, which is RFC 9110's optional-whitespace rule. A client that pads its own
    valid key is still that client, so 200 is right, and the parser correctly does not
    re-implement the trim.

    Whitespace INSIDE the credential is a different thing entirely: it is part of a segment,
    so it changes the digest or breaks the ref. That must stay a 401 — a parser that
    normalized interior whitespace would make the secret comparison fuzzy in its middle,
    which is where fuzziness turns into a forgeable credential.

    Pinned because the two look like one case and are not."""
    full = await issue_key()
    scheme, ref, secret = full.split("_", 2)

    for padded in (f" {full}", f"{full} ", f"\t{full}\t", f"  {full}  "):
        assert (await client.get(_GUARDED, headers=_bearer(padded))).status_code == 200

    for interior in (
        f"{scheme} _{ref}_{secret}",
        f"{scheme}_ {ref}_{secret}",
        f"{scheme}_{ref} _{secret}",
        f"{scheme}_{ref}_{secret[:1]} {secret[1:]}",
    ):
        assert (await client.get(_GUARDED, headers=_bearer(interior))).status_code == 401


async def test_uuid_ref_aliases_are_inert(
    client: AsyncClient, issue_key: IssuedKey, admin_user: ProvisionedUser
) -> None:
    """`uuid.UUID(hex=...)` is lenient: braces, dashes, a `urn:uuid:` prefix, a leading
    space or `+` or `0x`, and non-ASCII decimal digits all parse to a valid UUID. So the
    ref segment is NOT canonical, and several distinct strings name the same tenant.

    That is tolerable only because the ref is not a credential — it names the tenancy the
    lookup runs under, and the caller could have written the real UUID anyway. Pin the
    property: an alias of the caller's OWN tenant still authenticates (the alias is not a
    denial of service), and an alias buys no access the plain form would not.
    """
    full = await issue_key()
    scheme, ref, secret = full.split("_", 2)
    assert ref == admin_user.tenant_id.hex

    for alias in (
        str(admin_user.tenant_id),  # dashed
        "{" + ref + "}",
        "urn:uuid:" + str(admin_user.tenant_id),
        ref.upper(),
    ):
        response = await client.get(_GUARDED, headers=_bearer(f"{scheme}_{alias}_{secret}"))
        assert response.status_code == 200, f"alias {alias!r} -> {response.status_code}"

    # ...and the same aliasing applied to a ref the caller has no key in still fails.
    other = uuid.uuid4()
    for alias in (other.hex, str(other), "{" + other.hex + "}"):
        response = await client.get(_GUARDED, headers=_bearer(f"{scheme}_{alias}_{secret}"))
        assert response.status_code == 401, f"foreign alias {alias!r} -> {response.status_code}"


# --- The JWT credential shape must survive the new branch ---------------------


def test_a_real_jwt_is_never_parsed_as_an_api_key(provisioned_user: ProvisionedUser) -> None:
    """base64url's 63rd character is '_', so a JWT routinely carries underscores. If
    parse_api_key ever claimed one, get_current_user would short-circuit and the whole JWT
    path would go dark. 200 tokens, because whether a given JWT contains two underscores is
    luck of the signature."""
    for _ in range(200):
        token = encode_access(
            provisioned_user.user_id, provisioned_user.tenant_id, uuid.uuid4(), 0
        )

        assert parse_api_key(token) is None


async def test_jwt_authentication_still_works(admin_client: AsyncClient) -> None:
    """The other half of the short-circuit: a real bearer token still reaches its route."""
    response = await admin_client.get(_GUARDED)

    assert response.status_code == 200, response.text


# --- Minting is unpredictable -------------------------------------------------


def test_minted_secrets_are_csprng_and_unique() -> None:
    """256 bits from `secrets`, never a repeat, and no character outside the urlsafe
    alphabet (anything else would mean the secret is not what it claims to be)."""
    seen: set[tuple[str, str]] = set()
    for _ in range(500):
        full, digest = mint_api_key(uuid.uuid4())
        secret = full.split("_", 2)[2]

        assert len(secret) >= 43, f"secret is only {len(secret)} chars"
        assert set(secret) <= set(string.ascii_letters + string.digits + "-_")
        seen.add((full, digest))

    assert len(seen) == 500


def test_auth_module_never_uses_the_random_module() -> None:
    """`random` is a Mersenne Twister — its whole state is recoverable from 624 outputs, so
    one minted key would predict the next. A source-level guard, because the swap is a
    one-word edit that no functional test would notice."""
    source = inspect.getsource(auth_module)

    assert "import random" not in source
    assert "random." not in source
    assert "secrets." in source

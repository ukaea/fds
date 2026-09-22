#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "pyjwt>=2.14.0",
#     "cryptography>=46.0.0",
# ]
# ///
"""Mint FDS access tokens from a key you hold, with no identity provider.

FDS accepts a token when it is signed by a key belonging to an issuer listed in
FDS_TRUSTED_IDPS. Normally those keys are fetched from the identity provider.
An issuer configured with `jwks_file` instead reads them from disk, which lets
you sign tokens yourself:

    uv run scripts/mint-token.py init --out-dir dev
        writes dev/local-issuer.key (keep this private) and
        dev/local-issuer.jwks.json (give this to FDS)

    FDS_TRUSTED_IDPS='[{"issuer":"urn:fds:local","jwks_file":"dev/local-issuer.jwks.json"}]'

    uv run scripts/mint-token.py mint --key dev/local-issuer.key
        prints a token; add --scope, --subject, --minutes as needed

This is for bootstrapping a deployment, for automation, and for getting in when
the identity provider is unavailable. It is not a way for people to log in: it
bypasses whatever sign-in controls your institution applies, and a minted token
cannot be withdrawn before it expires. Keep the private key somewhere safe,
keep lifetimes short, and remove the issuer from FDS_TRUSTED_IDPS to revoke.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

DEFAULT_ISSUER = "urn:fds:local"
DEFAULT_KEY_ID = "local-1"


def init(args: argparse.Namespace) -> int:
    out_dir: Path = args.out_dir
    key_path = out_dir / "local-issuer.key"
    jwks_path = out_dir / "local-issuer.jwks.json"

    if key_path.exists() and not args.force:
        print(f"{key_path} exists; pass --force to replace it", file=sys.stderr)
        return 1

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    out_dir.mkdir(parents=True, exist_ok=True)

    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)

    jwk = json.loads(RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk |= {"kid": args.key_id, "alg": "RS256", "use": "sig"}
    jwks_path.write_text(json.dumps({"keys": [jwk]}, indent=2) + "\n")

    print(f"private key  {key_path}  (keep this secret, do not commit it)")
    print(f"public keys  {jwks_path}  (point FDS_TRUSTED_IDPS at this)")
    return 0


def mint(args: argparse.Namespace) -> int:
    try:
        private_key = serialization.load_pem_private_key(
            args.key.read_bytes(), password=None
        )
    except (OSError, ValueError) as e:
        print(f"could not read {args.key}: {e}", file=sys.stderr)
        return 1

    if not isinstance(private_key, rsa.RSAPrivateKey):
        print(f"{args.key} is not an RSA private key", file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "iss": args.issuer,
            "sub": args.subject,
            "aud": args.audience,
            "scope": " ".join(args.scope),
            "iat": now,
            "exp": now + timedelta(minutes=args.minutes),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": args.key_id},
    )
    print(token)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="generate a key pair")
    p_init.add_argument("--out-dir", type=Path, default=Path("dev"))
    p_init.add_argument("--key-id", default=DEFAULT_KEY_ID)
    p_init.add_argument(
        "--force", action="store_true", help="replace an existing key pair"
    )
    p_init.set_defaults(func=init)

    p_mint = sub.add_parser("mint", help="sign a token")
    p_mint.add_argument("--key", type=Path, default=Path("dev/local-issuer.key"))
    p_mint.add_argument("--key-id", default=DEFAULT_KEY_ID)
    p_mint.add_argument("--issuer", default=DEFAULT_ISSUER)
    p_mint.add_argument("--audience", default="fds-client")
    p_mint.add_argument("--subject", default="local-operator")
    p_mint.add_argument(
        "--scope",
        nargs="+",
        default=["fds-admin"],
        help="scopes to grant, space separated (default: fds-admin)",
    )
    p_mint.add_argument(
        "--minutes", type=int, default=15, help="token lifetime (default: 15)"
    )
    p_mint.set_defaults(func=mint)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

# Auth Contract: WalletProof Authorization

## Overview

Thoth authenticates principals (humans and agents) by their Tempo wallet address.
There are no email/password/API-key accounts in V1. Identity derives entirely from
cryptographic wallet ownership.

## Two paths, one principal

### Payment path (existing)

`Mpp.charge()` verifies a payment credential whose `source` field contains
`tempo:<address>`. The address is extracted, lowercased, and upserted into
`wallet_principals`. This path is used by paid content endpoints.

### Signature proof path (new)

For non-payment endpoints (publisher mutations, future settings), the server
issues an HMAC-bound nonce and the client signs it with EIP-191 `personal_sign`.

Both paths produce the same `wallet_address` (lowercase) and share the
`wallet_principals` table.

## WalletProof Authorization header

```
Authorization: WalletProof <challenge_id>.<hex_signature>
```

- `challenge_id`: The nonce returned by `POST /auth/challenge`.
- `hex_signature`: The EIP-191 `personal_sign` signature of the challenge id,
  hex-encoded (with or without `0x` prefix; both are accepted).

## Challenge lifecycle

1. Client calls `POST /auth/challenge`.
   Response: `{"challenge": "<nonce>", "realm": "<realm>"}`.

2. Client signs the nonce with `personal_sign(nonce)` using their wallet key.

3. Client attaches the proof to subsequent requests:
   `Authorization: WalletProof <nonce>.<signature>`

4. Server reconstructs the Challenge from the nonce, verifies the HMAC, recovers
   the signer via `eth_account.Account.recover_message`, lowercases the address,
   and upserts into `wallet_principals`.

## Shared principal model

Whether a request arrives from a browser wallet (MetaMask `personal_sign`) or an
agent (`eth_account.Account.sign_message`), the resulting `WalletPrincipal` is
identical: a lowercase Ethereum address stored in `wallet_principals`.

## Endpoints

| Method | Path                    | Auth required | Description                    |
|--------|-------------------------|---------------|--------------------------------|
| POST   | /auth/challenge         | No            | Issue a signable nonce         |
| PATCH  | /publishers/{handle}    | WalletProof   | Update publisher display name  |

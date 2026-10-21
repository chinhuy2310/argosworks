#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""crypto.py — JARVIS 보안 & 시크릿 관리 (AES-256 + HMAC-SHA256 Authenticated Encryption)
마스터 키(JARVIS_MASTER_KEY)를 기반으로 API 토큰, AI 키 등을 안전하게 암호화/복호화합니다.
외부 pip 라이브러리(C 의존성) 없이도 모든 OS/플랫폼에서 100% 동작하는 표준 AES-256 구현체입니다.
"""

import os
import sys
import base64
import hashlib
import hmac
import secrets

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SERVER_DIR)
ENV_PATH = os.path.join(BASE_DIR, ".env")

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives import padding as crypto_padding
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False

# Standard AES S-Box & Inverted S-Box
_S_BOX = [
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16
]

_INV_S_BOX = [0] * 256
for _i, _v in enumerate(_S_BOX):
    _INV_S_BOX[_v] = _i

_RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36]


def _sub_word(w):
    return ((_S_BOX[(w >> 24) & 0xFF] << 24) |
            (_S_BOX[(w >> 16) & 0xFF] << 16) |
            (_S_BOX[(w >> 8) & 0xFF] << 8) |
            (_S_BOX[w & 0xFF]))


def _rot_word(w):
    return ((w << 8) & 0xFFFFFFFF) | (w >> 24)


def _key_expansion(key_bytes):
    # AES-256: 32 bytes key, 14 rounds, 60 words
    words = []
    for i in range(8):
        words.append(int.from_bytes(key_bytes[i*4:(i+1)*4], 'big'))
    for i in range(8, 60):
        temp = words[i - 1]
        if i % 8 == 0:
            temp = _sub_word(_rot_word(temp)) ^ (_RCON[i // 8] << 24)
        elif i % 8 == 4:
            temp = _sub_word(temp)
        words.append(words[i - 8] ^ temp)
    
    round_keys = []
    for r in range(15):
        rk = []
        for c in range(4):
            w = words[r * 4 + c]
            rk.extend([(w >> 24) & 0xFF, (w >> 16) & 0xFF, (w >> 8) & 0xFF, w & 0xFF])
        round_keys.append(rk)
    return round_keys


def _xtime(a):
    return (((a << 1) ^ 0x1B) & 0xFF) if (a & 0x80) else (a << 1)


def _mul(a, b):
    res = 0
    for _ in range(8):
        if b & 1:
            res ^= a
        a = _xtime(a)
        b >>= 1
    return res


def _cipher_block(block, round_keys):
    state = list(block)
    for i in range(16):
        state[i] ^= round_keys[0][i]
    
    for r in range(1, 14):
        for i in range(16):
            state[i] = _S_BOX[state[i]]
        s = state
        state = [
            s[0], s[5], s[10], s[15],
            s[4], s[9], s[14], s[3],
            s[8], s[13], s[2], s[7],
            s[12], s[1], s[6], s[11]
        ]
        new_s = [0] * 16
        for c in range(4):
            c4 = c * 4
            a0, a1, a2, a3 = state[c4], state[c4+1], state[c4+2], state[c4+3]
            new_s[c4]   = _xtime(a0) ^ (_xtime(a1) ^ a1) ^ a2 ^ a3
            new_s[c4+1] = a0 ^ _xtime(a1) ^ (_xtime(a2) ^ a2) ^ a3
            new_s[c4+2] = a0 ^ a1 ^ _xtime(a2) ^ (_xtime(a3) ^ a3)
            new_s[c4+3] = (_xtime(a0) ^ a0) ^ a1 ^ a2 ^ _xtime(a3)
        state = new_s
        for i in range(16):
            state[i] ^= round_keys[r][i]
            
    for i in range(16):
        state[i] = _S_BOX[state[i]]
    s = state
    state = [
        s[0], s[5], s[10], s[15],
        s[4], s[9], s[14], s[3],
        s[8], s[13], s[2], s[7],
        s[12], s[1], s[6], s[11]
    ]
    for i in range(16):
        state[i] ^= round_keys[14][i]
    return bytes(state)


def _inv_cipher_block(block, round_keys):
    state = list(block)
    for i in range(16):
        state[i] ^= round_keys[14][i]
        
    for r in range(13, 0, -1):
        s = state
        state = [
            s[0], s[13], s[10], s[7],
            s[4], s[1], s[14], s[11],
            s[8], s[5], s[2], s[15],
            s[12], s[9], s[6], s[3]
        ]
        for i in range(16):
            state[i] = _INV_S_BOX[state[i]]
        for i in range(16):
            state[i] ^= round_keys[r][i]
        new_s = [0] * 16
        for c in range(4):
            c4 = c * 4
            a0, a1, a2, a3 = state[c4], state[c4+1], state[c4+2], state[c4+3]
            new_s[c4]   = _mul(a0, 0x0e) ^ _mul(a1, 0x0b) ^ _mul(a2, 0x0d) ^ _mul(a3, 0x09)
            new_s[c4+1] = _mul(a0, 0x09) ^ _mul(a1, 0x0e) ^ _mul(a2, 0x0b) ^ _mul(a3, 0x0d)
            new_s[c4+2] = _mul(a0, 0x0d) ^ _mul(a1, 0x09) ^ _mul(a2, 0x0e) ^ _mul(a3, 0x0b)
            new_s[c4+3] = _mul(a0, 0x0b) ^ _mul(a1, 0x0d) ^ _mul(a2, 0x09) ^ _mul(a3, 0x0e)
        state = new_s

    s = state
    state = [
        s[0], s[13], s[10], s[7],
        s[4], s[1], s[14], s[11],
        s[8], s[5], s[2], s[15],
        s[12], s[9], s[6], s[3]
    ]
    for i in range(16):
        state[i] = _INV_S_BOX[state[i]]
    for i in range(16):
        state[i] ^= round_keys[0][i]
    return bytes(state)


def _aes256_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    if _HAS_CRYPTOGRAPHY:
        padder = crypto_padding.PKCS7(128).padder()
        padded_data = padder.update(plaintext) + padder.finalize()
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()
        return encryptor.update(padded_data) + encryptor.finalize()

    pad_len = 16 - (len(plaintext) % 16)
    padded = plaintext + bytes([pad_len] * pad_len)
    round_keys = _key_expansion(key)
    ciphertext = bytearray()
    prev = iv
    for i in range(0, len(padded), 16):
        block = bytes(padded[i+j] ^ prev[j] for j in range(16))
        enc = _cipher_block(block, round_keys)
        ciphertext.extend(enc)
        prev = enc
    return bytes(ciphertext)


def _aes256_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    if len(ciphertext) % 16 != 0 or not ciphertext:
        raise ValueError("Invalid ciphertext length")

    if _HAS_CRYPTOGRAPHY:
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_plain = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = crypto_padding.PKCS7(128).unpadder()
        return unpadder.update(padded_plain) + unpadder.finalize()

    round_keys = _key_expansion(key)
    plaintext = bytearray()
    prev = iv
    for i in range(0, len(ciphertext), 16):
        enc_block = ciphertext[i:i+16]
        dec = _inv_cipher_block(enc_block, round_keys)
        plain_block = bytes(dec[j] ^ prev[j] for j in range(16))
        plaintext.extend(plain_block)
        prev = enc_block
    pad_len = plaintext[-1]
    if pad_len < 1 or pad_len > 16 or plaintext[-pad_len:] != bytes([pad_len] * pad_len):
        raise ValueError("Invalid PKCS#7 padding")
    return bytes(plaintext[:-pad_len])


# ---------------------------------------------------------------------------
# Master Key Management & Derivation
# ---------------------------------------------------------------------------
_CACHED_MASTER_KEY = None


def get_master_key() -> bytes:
    """Return 32-byte master key from environment or .env, auto-generating if absent."""
    global _CACHED_MASTER_KEY
    if _CACHED_MASTER_KEY is not None:
        return _CACHED_MASTER_KEY

    raw_key = os.environ.get("JARVIS_MASTER_KEY", "").strip()

    # If not in environ, check .env file
    if not raw_key and os.path.isfile(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("JARVIS_MASTER_KEY=") and not line.startswith("#"):
                        raw_key = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass

    # If still not found, auto-generate and persist to .env
    if not raw_key:
        generated_hex = secrets.token_hex(32)  # 256 bits = 64 hex chars
        raw_key = generated_hex
        try:
            with open(ENV_PATH, "a", encoding="utf-8") as f:
                f.write(f"\n# JARVIS Master Key for Secret Encryption (AES-256)\nJARVIS_MASTER_KEY={generated_hex}\n")
        except Exception as e:
            print(f"[Crypto] Warning: could not persist JARVIS_MASTER_KEY to .env: {e}", file=sys.stderr)

    os.environ["JARVIS_MASTER_KEY"] = raw_key

    # Derive 32 bytes using SHA-256
    _CACHED_MASTER_KEY = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return _CACHED_MASTER_KEY


def _derive_keys(master_key: bytes):
    enc_key = hashlib.sha256(master_key + b":enc_key_v1").digest()
    mac_key = hashlib.sha256(master_key + b":mac_key_v1").digest()
    return enc_key, mac_key


PREFIX = "enc:v1:"


def is_encrypted(val: str) -> bool:
    """Check if value is in encrypted format."""
    return bool(val and isinstance(val, str) and val.startswith(PREFIX))


def encrypt_secret(val: str) -> str:
    """Encrypt a string secret using AES-256 + HMAC-SHA256 authenticated encryption.
    Returns string prefixed with 'enc:v1:'. If already encrypted or empty, returns as is.
    """
    if not val or not isinstance(val, str):
        return val or ""
    val_str = val.strip()
    if not val_str:
        return ""
    if is_encrypted(val_str):
        return val_str

    try:
        master_key = get_master_key()
        enc_key, mac_key = _derive_keys(master_key)
        iv = secrets.token_bytes(16)
        plaintext_bytes = val_str.encode("utf-8")
        ciphertext = _aes256_cbc_encrypt(plaintext_bytes, enc_key, iv)
        # Encrypt-then-MAC: HMAC covers IV + ciphertext
        mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()
        payload = iv + mac + ciphertext
        return PREFIX + base64.b64encode(payload).decode("ascii")
    except Exception as e:
        print(f"[Crypto] Encryption failed: {e}", file=sys.stderr)
        return val_str


def decrypt_secret(val: str) -> str:
    """Decrypt a secret prefixed with 'enc:v1:'.
    If not encrypted (plain text), returns the string as is for 100% backward compatibility.
    """
    if not val or not isinstance(val, str):
        return val or ""
    val_str = val.strip()
    if not is_encrypted(val_str):
        return val_str

    try:
        raw_b64 = val_str[len(PREFIX):]
        payload = base64.b64decode(raw_b64)
        if len(payload) < 16 + 32 + 16:  # IV(16) + MAC(32) + at least 1 AES block(16)
            return val_str

        iv = payload[:16]
        expected_mac = payload[16:48]
        ciphertext = payload[48:]

        master_key = get_master_key()
        enc_key, mac_key = _derive_keys(master_key)

        # Authenticate MAC
        actual_mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(actual_mac, expected_mac):
            print("[Crypto] HMAC verification failed — ciphertext tampered or invalid master key", file=sys.stderr)
            return ""

        plaintext_bytes = _aes256_cbc_decrypt(ciphertext, enc_key, iv)
        return plaintext_bytes.decode("utf-8")
    except Exception as e:
        print(f"[Crypto] Decryption failed: {e}", file=sys.stderr)
        return val_str

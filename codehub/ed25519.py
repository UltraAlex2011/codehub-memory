# Ed25519 signatures (RFC 8032), standard library only. Code Hub installs a
# premium package only if its manifest carries a valid signature of the
# publisher's key - a modified copy is refused. Slow but exact; it runs once
# per install. Signing is used by tools/build_premium.py on the publisher's
# machine; the secret key never leaves it.
import hashlib

P = 2 ** 255 - 19
L = 2 ** 252 + 27742317777372353535851937790883648493
D = -121665 * pow(121666, P - 2, P) % P
I = pow(2, (P - 1) // 4, P)


def _xrecover(y):
    xx = (y * y - 1) * pow(D * y * y + 1, P - 2, P)
    x = pow(xx, (P + 3) // 8, P)
    if (x * x - xx) % P:
        x = x * I % P
    if x % 2:
        x = P - x
    return x


_BY = 4 * pow(5, P - 2, P) % P
B = (_xrecover(_BY), _BY, 1, _xrecover(_BY) * _BY % P)      # extended coordinates
ZERO = (0, 1, 1, 0)


def _add(p, q):
    a = (p[1] - p[0]) * (q[1] - q[0]) % P
    b = (p[1] + p[0]) * (q[1] + q[0]) % P
    c = 2 * p[3] * q[3] * D % P
    d = 2 * p[2] * q[2] % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return e * f % P, g * h % P, f * g % P, e * h % P


def _mul(s, p):
    q = ZERO
    while s:
        if s & 1:
            q = _add(q, p)
        p = _add(p, p)
        s >>= 1
    return q


def _encode(p):
    zi = pow(p[2], P - 2, P)
    x, y = p[0] * zi % P, p[1] * zi % P
    return (y | ((x & 1) << 255)).to_bytes(32, 'little')


def _decode(s):
    if len(s) != 32:
        raise ValueError('bad point')
    y = int.from_bytes(s, 'little')
    sign, y = y >> 255, y & ((1 << 255) - 1)
    if y >= P:
        raise ValueError('bad point')
    x = _xrecover(y)
    if (x * x * -1 + y * y - 1 - D * x * x * y * y) % P:
        raise ValueError('not on curve')
    if x & 1 != sign:
        x = P - x
    return x, y, 1, x * y % P


def _equal(p, q):
    return (p[0] * q[2] - q[0] * p[2]) % P == 0 and (p[1] * q[2] - q[1] * p[2]) % P == 0


def _h(*parts):
    return int.from_bytes(hashlib.sha512(b''.join(parts)).digest(), 'little')


def _secret(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], 'little')
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    return _encode(_mul(_secret(seed)[0], B))


def sign(seed, message):
    a, prefix = _secret(seed)
    pub = _encode(_mul(a, B))
    r = _h(prefix, message) % L
    big_r = _encode(_mul(r, B))
    s = (r + _h(big_r, pub, message) * a) % L
    return big_r + s.to_bytes(32, 'little')


def verify(pub, message, signature):
    try:
        if len(signature) != 64:
            return False
        a = _decode(pub)
        big_r = _decode(signature[:32])
        s = int.from_bytes(signature[32:], 'little')
        if s >= L:
            return False
        k = _h(signature[:32], pub, message) % L
        return _equal(_mul(s, B), _add(big_r, _mul(k, a)))
    except ValueError:
        return False

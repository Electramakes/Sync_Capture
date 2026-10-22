"""Creates key.pem and cert.pem (self-signed, valid 30 days) for the local HTTPS server.
Run once:  python make_cert.py
"""
import datetime
import ipaddress
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # no packet is sent; just finds the LAN address
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


ip = lan_ip()
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
san = x509.SubjectAlternativeName([
    x509.DNSName("localhost"),
    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
    x509.IPAddress(ipaddress.ip_address(ip)),
])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (
    x509.CertificateBuilder()
    .subject_name(name)
    .issuer_name(name)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(now)
    .not_valid_after(now + datetime.timedelta(days=30))
    .add_extension(san, critical=False)
    .sign(key, hashes.SHA256())
)

with open("key.pem", "wb") as f:
    f.write(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
with open("cert.pem", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print(f"Created key.pem and cert.pem (valid for localhost, 127.0.0.1 and {ip})")

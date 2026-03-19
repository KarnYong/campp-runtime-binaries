# CAMPP Runtime Binaries - Download Links & SHA256 Checksums

This document contains all download URLs and SHA256 checksums for verifying file integrity.

## MySQL 8.4.0

| File | SHA256 | Download URL |
|------|--------|--------------|
| mysql-8.4.0-winx64.zip | `fb1f0c6cce229be4b3208bec8a605576bb47eabb00512bccbcc4396af332c25c` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/mysql-8.4.0/mysql-8.4.0-winx64.zip) |
| mysql-8.4.0-linux-glibc2.28-x86_64.tar.xz | `377666d81b81efd2510c1e12794a088a98412ede4a01f0b94110fa1549734ae3` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/mysql-8.4.0/mysql-8.4.0-linux-glibc2.28-x86_64.tar.xz) |
| mysql-8.4.0-linux-glibc2.28-aarch64.tar.xz | `f4d9186929bb26046a3bd1a3b8b74bd235e7ec69318f09ad7218cfcc0070939b` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/mysql-8.4.0/mysql-8.4.0-linux-glibc2.28-aarch64.tar.xz) |
| mysql-8.4.0-macos14-x86_64.tar.gz | `adbb8b7e261547768a548d97938a5f1b66cf85daee09db28ac4bb657aa7d4192` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/mysql-8.4.0/mysql-8.4.0-macos14-x86_64.tar.gz) |
| mysql-8.4.0-macos14-arm64.tar.gz | `b4ad74a78aa4378df00e1164c9979dd660ea09bf47e05f6ef8324f4ea1418618` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/mysql-8.4.0/mysql-8.4.0-macos14-arm64.tar.gz) |

## PHP 8.5.1 & 8.4.18

| File | SHA256 | Download URL |
|------|--------|--------------|
| php-8.5.1-Win32-vs17-x64.zip | `77fbee57c8159279bc065942d361103b0a3f53c8dfabc182a07433be9eec8dba` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/php-8.5.1/php-8.5.1-Win32-vs17-x64.zip) |
| php-8.5.1-Win32-vs17-x86.zip | `cfd66a27d32e0ce2f462527f8f29fd2d797c714083c07a32b6147d06a7553d6f` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/php-8.5.1/php-8.5.1-Win32-vs17-x86.zip) |
| php-8.4.18-fpm-linux-x86_64.tar.gz | `b3871bc4e2d99140d3cba88ec0fe54d828ee2e460a6232f6d74565a288420e62` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/php-8.5.1/php-8.4.18-fpm-linux-x86_64.tar.gz) |
| php-8.4.18-fpm-linux-aarch64.tar.gz | `2b70ddcf7542db5c29b9d1b01a3dce95e0f0a35ee0b69e77b7aa3fed4b6c6f9c` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/php-8.5.1/php-8.4.18-fpm-linux-aarch64.tar.gz) |
| php-8.4.18-fpm-macos-x86_64.tar.gz | `6a211936907b9df16ae32fa8cdaa74d76b7ce3940e09cf5fba0109140953db98` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/php-8.5.1/php-8.4.18-fpm-macos-x86_64.tar.gz) |
| php-8.4.18-fpm-macos-aarch64.tar.gz | `9fb9a6a5ce41a384a611ec3f3e2deb5329ef0ce68848ab50ac7bb391b1890c23` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/php-8.5.1/php-8.4.18-fpm-macos-aarch64.tar.gz) |

## phpMyAdmin 5.2.2

| File | SHA256 | Download URL |
|------|--------|--------------|
| phpMyAdmin-5.2.2-all-languages.zip | `6b99534f72ffb1d7275f50d23ca4141e1495c97d7cadb73a41d6dc580ed5ce29` | [Download](https://github.com/KarnYong/campp-runtime-binaries/releases/download/phpmyadmin-5.2.2/phpMyAdmin-5.2.2-all-languages.zip) |

## How to Verify SHA256 Checksums

### Windows (PowerShell)
```powershell
CertUtil -hashinfile mysql-8.4.0-winx64.zip SHA256
```

### Linux / macOS
```bash
sha256sum mysql-8.4.0-winx64.zip
# or on macOS:
shasum -a 256 mysql-8.4.0-winx64.zip
```

## Base URL Pattern

```
https://github.com/KarnYong/campp-runtime-binaries/releases/download/{tag}/{filename}
```

- MySQL files: tag = `mysql-8.4.0`
- PHP files: tag = `php-8.5.1`
- phpMyAdmin files: tag = `phpmyadmin-5.2.2`

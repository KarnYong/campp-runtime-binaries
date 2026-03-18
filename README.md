# CAMPP Runtime Binaries

> Binary distributions for CAMPP (Caddy + MySQL + PHP + phpMyAdmin) - A cross-platform local web development stack.

This repository hosts pre-compiled runtime binaries used by [CAMPP](https://github.com/karnyong/campp) to avoid download issues with upstream servers and provide consistent, reliable downloads.

## 📦 Available Binaries

| Component | Versions | Platforms | Status |
|-----------|----------|-----------|--------|
| **Caddy** | 2.8.4 | Windows x64/ARM64, macOS x64/ARM64, Linux x64/ARM64 | ✅ Stable |
| **PHP** | 8.5.x, 8.4.x, 8.3.x, 8.2.x | Windows x64/ARM64, macOS x64/ARM64, Linux x64/ARM64 | ✅ Stable |
| **MySQL** | 8.4.x, 8.0.x | Windows x64/ARM64, macOS x64/ARM64, Linux x64/ARM64 | ✅ Stable |
| **phpMyAdmin** | 5.2.x | Universal (ZIP) | ✅ Stable |

## 🚀 Usage

### For CAMPP Users

These binaries are automatically downloaded by CAMPP. No manual action required.

### Manual Download

You can download binaries directly from the [Releases](https://github.com/karnyong/campp-runtime-binaries/releases) page.

**Example download URLs:**
```
https://github.com/karnyong/campp-runtime-binaries/releases/download/v1.0.0/mysql-8.4.0-winx64.zip
https://github.com/karnyong/campp-runtime-binaries/releases/download/v1.0.0/php-8.5.1-Win32-vs17-x64.zip
```

## 🔄 Updating Binaries

When updating to new versions of components, follow these steps:

### 1. Download the Official Binary

Visit the official source:
- **Caddy:** https://caddyserver.com/download
- **PHP:** https://windows.php.net/download/ or https://static-php.dev/
- **MySQL:** https://dev.mysql.com/downloads/mysql/
- **phpMyAdmin:** https://www.phpmyadmin.net/downloads/

### 2. Create a New Release

```bash
# Using GitHub CLI
gh release create v1.1.0 \
  --title "CAMPP Runtime Binaries v1.1.0" \
  --notes "Update PHP to 8.5.2, MySQL to 8.4.1"

# Upload files
gh release upload v1.1.0 ./path/to/mysql-8.4.1-winx64.zip
gh release upload v1.1.0 ./path/to/php-8.5.2-Win32-vs17-x64.zip
# ... etc
```

### 3. Update CAMPP Configuration

Update `runtime-config.json` in the main CAMPP repository:

```json
{
  "binaries": {
    "mysql": {
      "versions": [
        {
          "id": "mysql-8.4.1",
          "version": "8.4.1",
          "selected": true,
          "urls": {
            "windowsX64": "https://github.com/karnyong/campp-runtime-binaries/releases/download/v1.1.0/mysql-8.4.1-winx64.zip"
          }
        }
      ]
    }
  }
}
```

## 📋 File Naming Convention

Follow this pattern for consistency:

```
{component}-{version}-{platform}.{extension}
```

**Examples:**
- `mysql-8.4.0-winx64.zip`
- `php-8.5.1-Win32-vs17-x64.zip`
- `caddy-2.8.4-windows-amd64.zip`
- `phpmyadmin-5.2.2-all-languages.zip`

## 🔒 Security & Integrity

- All binaries are downloaded from official upstream sources
- No modifications are made to the binaries
- SHA256 checksums can be verified against upstream releases

## 📝 License

The binaries in this repository are subject to their respective licenses:

- **Caddy:** Apache 2.0 License
- **PHP:** PHP License 3.01
- **MySQL:** GPL v2 License
- **phpMyAdmin:** GPL v2 License

See the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

When adding new binaries or updating versions:

1. **Verify the source** - Only download from official sources
2. **Test the binary** - Ensure it works on the target platform
3. **Update the release notes** - Document what changed
4. **Update CAMPP config** - Modify `runtime-config.json` accordingly

## 📦 Component Sources

| Component | Official Website | License |
|-----------|------------------|---------|
| [Caddy](https://caddyserver.com/) | https://github.com/caddyserver/caddy | Apache 2.0 |
| [PHP](https://www.php.net/) | https://www.php.net/downloads | PHP 3.01 |
| [MySQL](https://www.mysql.com/) | https://www.mysql.com/downloads | GPL v2 |
| [phpMyAdmin](https://www.phpmyadmin.net/) | https://www.phpmyadmin.net | GPL v2 |

## 🔗 Links

- [CAMPP Main Repository](https://github.com/karnyong/campp)
- [CAMPP Documentation](https://github.com/karnyong/campp/wiki)
- [Issue Tracker](https://github.com/karnyong/campp/issues)

## 📄 License Statement

This repository contains binary distributions of the following software:

- Caddy web server © 2015-2024 Matthew Holt and Caddy contributors
- PHP © The PHP Group
- MySQL © Oracle Corporation
- phpMyAdmin © The phpMyAdmin Project

Each component is distributed under its own license terms. Please refer to the respective project websites for full license information.

---

**Note:** This repository is maintained as a convenience for CAMPP users. For the most up-to-date versions, please visit the official project websites.

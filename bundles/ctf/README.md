# ctf bundles : vulnerable containers for training

One vulnerable container per bundle, deployed with docker-compose from the matching element of range42-catalog (`03_container_layer/docker/_ctf/`, mirrored exactly) on one target VM of the scenario. The five parameters are the same for every bundle : the target VM (`global_vm_ssh_name`), the operator user, the remote compose directory, its cleanup once the stack is up, and whether the proof-of-concept files ship along.

The taxonomy follows the catalog : `cve/<domain>/<product>/<CVE-id>` and `misconfiguration/<domain>/<service>`. The tier is open-ended, the path of a bundle may be deeper than in the other tiers.

16 bundles. Every bundle is a playbook, `main.yml`, imported at parse time through `RANGE42_BUNDLE_DIR` ; its caller-facing parameters are declared in `bundle_parameters.src.yml` and published as `bundle_parameters.json` (see [../README.md](../README.md)).

## cve/crypto

| Bundle | What it does | Parameters |
|---|---|---|
| [`cve/crypto/openssl/CVE-2014-0160`](cve/crypto/openssl/CVE-2014-0160/README.md) | Deploy the OpenSSL Heartbleed (CVE-2014-0160) vulnerable container via docker-compose for CTF training | 5, [json](cve/crypto/openssl/CVE-2014-0160/bundle_parameters.json), [src](cve/crypto/openssl/CVE-2014-0160/bundle_parameters.src.yml) |
| [`cve/crypto/openssl/CVE-2022-0778`](cve/crypto/openssl/CVE-2022-0778/README.md) | Deploy the OpenSSL CVE-2022-0778 vulnerable container for CTF training via docker-compose | 5, [json](cve/crypto/openssl/CVE-2022-0778/bundle_parameters.json), [src](cve/crypto/openssl/CVE-2022-0778/bundle_parameters.src.yml) |

## cve/network

| Bundle | What it does | Parameters |
|---|---|---|
| [`cve/network/erlang-ssh/CVE-2025-32433`](cve/network/erlang-ssh/CVE-2025-32433/README.md) | Erlang/OTP SSH CVE-2025-32433 vulnerable container deployed via docker-compose for CTF training (exposed tcp 2225) | 5, [json](cve/network/erlang-ssh/CVE-2025-32433/bundle_parameters.json), [src](cve/network/erlang-ssh/CVE-2025-32433/bundle_parameters.src.yml) |
| [`cve/network/openssh/CVE-2018-15473`](cve/network/openssh/CVE-2018-15473/README.md) | Deploy the vulnerable OpenSSH username-enumeration (CVE-2018-15473) container for CTF training | 5, [json](cve/network/openssh/CVE-2018-15473/bundle_parameters.json), [src](cve/network/openssh/CVE-2018-15473/bundle_parameters.src.yml) |
| [`cve/network/openssh/CVE-2024-6387`](cve/network/openssh/CVE-2024-6387/README.md) | Deploy the vulnerable OpenSSH regreSSHion (CVE-2024-6387) container for CTF training | 5, [json](cve/network/openssh/CVE-2024-6387/bundle_parameters.json), [src](cve/network/openssh/CVE-2024-6387/bundle_parameters.src.yml) |

## cve/system

| Bundle | What it does | Parameters |
|---|---|---|
| [`cve/system/sudo/CVE-2023-22809`](cve/system/sudo/CVE-2023-22809/README.md) | Deploy the vulnerable sudoedit (CVE-2023-22809) container for CTF training | 5, [json](cve/system/sudo/CVE-2023-22809/bundle_parameters.json), [src](cve/system/sudo/CVE-2023-22809/bundle_parameters.src.yml) |
| [`cve/system/sudo/CVE-2025-32462`](cve/system/sudo/CVE-2025-32462/README.md) | Deploy the vulnerable sudo host-option (CVE-2025-32462) container for CTF training | 5, [json](cve/system/sudo/CVE-2025-32462/bundle_parameters.json), [src](cve/system/sudo/CVE-2025-32462/bundle_parameters.src.yml) |
| [`cve/system/sudo/CVE-2025-32463`](cve/system/sudo/CVE-2025-32463/README.md) | Deploys the sudo CVE-2025-32463 vulnerable container via docker-compose for CTF training (exposed tcp port 1113) | 5, [json](cve/system/sudo/CVE-2025-32463/bundle_parameters.json), [src](cve/system/sudo/CVE-2025-32463/bundle_parameters.src.yml) |

## cve/web

| Bundle | What it does | Parameters |
|---|---|---|
| [`cve/web/apache/CVE-2021-42013`](cve/web/apache/CVE-2021-42013/README.md) | Deploy the Apache HTTP Server (CVE-2021-42013) path-traversal RCE vulnerable container via docker-compose for CTF training | 5, [json](cve/web/apache/CVE-2021-42013/bundle_parameters.json), [src](cve/web/apache/CVE-2021-42013/bundle_parameters.src.yml) |
| [`cve/web/pdfjs/CVE-2024-4367`](cve/web/pdfjs/CVE-2024-4367/README.md) | Deploy the PDF.js CVE-2024-4367 vulnerable container for CTF training via docker-compose | 5, [json](cve/web/pdfjs/CVE-2024-4367/bundle_parameters.json), [src](cve/web/pdfjs/CVE-2024-4367/bundle_parameters.src.yml) |
| [`cve/web/php/CVE-2019-11043`](cve/web/php/CVE-2019-11043/README.md) | Deploy the PHP-FPM (CVE-2019-11043) vulnerable container via docker-compose for CTF training | 5, [json](cve/web/php/CVE-2019-11043/bundle_parameters.json), [src](cve/web/php/CVE-2019-11043/bundle_parameters.src.yml) |
| [`cve/web/tomcat/CVE-2025-24813`](cve/web/tomcat/CVE-2025-24813/README.md) | Deploy the vulnerable Apache Tomcat partial-PUT RCE (CVE-2025-24813) container for CTF training | 5, [json](cve/web/tomcat/CVE-2025-24813/bundle_parameters.json), [src](cve/web/tomcat/CVE-2025-24813/bundle_parameters.src.yml) |
| [`cve/web/uwsg_php/CVE-2018-7490`](cve/web/uwsg_php/CVE-2018-7490/README.md) | Deploys the uwsgi-php CVE-2018-7490 vulnerable container via docker-compose for CTF training | 5, [json](cve/web/uwsg_php/CVE-2018-7490/bundle_parameters.json), [src](cve/web/uwsg_php/CVE-2018-7490/bundle_parameters.src.yml) |
| [`cve/web/vite/CVE-2025-30208`](cve/web/vite/CVE-2025-30208/README.md) | Deploys the Vite dev server CVE-2025-30208 vulnerable container via docker-compose for CTF training | 5, [json](cve/web/vite/CVE-2025-30208/bundle_parameters.json), [src](cve/web/vite/CVE-2025-30208/bundle_parameters.src.yml) |

## misconfiguration/network

| Bundle | What it does | Parameters |
|---|---|---|
| [`misconfiguration/network/vsftpd/ftp_anon_server`](misconfiguration/network/vsftpd/ftp_anon_server/README.md) | Deploy the vsftpd anonymous FTP misconfiguration vulnerable container via docker-compose for CTF training | 5, [json](misconfiguration/network/vsftpd/ftp_anon_server/bundle_parameters.json), [src](misconfiguration/network/vsftpd/ftp_anon_server/bundle_parameters.src.yml) |

## misconfiguration/system

| Bundle | What it does | Parameters |
|---|---|---|
| [`misconfiguration/system/lpe-01`](misconfiguration/system/lpe-01/README.md) | Deploy the SUID-based Linux local privilege escalation misconfiguration vulnerable container via docker-compose for CTF training | 5, [json](misconfiguration/system/lpe-01/bundle_parameters.json), [src](misconfiguration/system/lpe-01/bundle_parameters.src.yml) |

Regenerate this index with `_tools/generate-bundle-index.py` after adding or re-describing a bundle.

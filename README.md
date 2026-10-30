# LAN Scanner

[![Build Docker image](https://github.com/Undermix96/lan-scanner/actions/workflows/docker.yml/badge.svg)](https://github.com/Undermix96/lan-scanner/actions/workflows/docker.yml)

Container Docker che scansiona periodicamente la tua LAN con **nmap**, cataloga tutti i dispositivi trovati (IP, MAC, vendor, hostname) e le loro **porte aperte** con i servizi in ascolto, e mostra il tutto in una **web UI**.

## Funzionalità

- Rilevamento automatico delle reti a cui è collegato l'host (oppure target manuali)
- Host discovery (ARP + ping + TCP SYN/ACK) e scansione delle porte con riconoscimento dei servizi (`-sV`)
- Catalogo persistente in SQLite: i dispositivi sono identificati per MAC address, quindi restano gli stessi anche se cambiano IP
- Stato online/offline, data di primo e ultimo avvistamento
- Alias e note personalizzabili per ogni dispositivo
- Ricerca/filtri, ordinamento, storico delle scansioni, esportazione CSV
- Scansione automatica a intervalli e pulsante "Scansiona ora"

## Avvio rapido

```bash
git clone https://github.com/Undermix96/lan-scanner.git
cd lan-scanner
docker compose up -d --build
```

Apri `http://<ip-del-server>:8080`.

> Il container usa `network_mode: host` e le capability `NET_RAW`/`NET_ADMIN`: servono per vedere la LAN direttamente (ARP, MAC address, vendor). Funziona su Linux; su Docker Desktop (macOS/Windows) la rete host non è la LAN reale, quindi imposta `SCAN_TARGETS` manualmente e aspettati di non vedere i MAC.

Immagine precompilata (amd64 e arm64, es. Raspberry Pi), pubblicata da GitHub Actions su GitHub Container Registry:

```bash
docker run -d --name lan-scanner --network host --cap-add NET_RAW --cap-add NET_ADMIN -v "$PWD/data:/data" ghcr.io/undermix96/lan-scanner:latest
```

Per usarla con compose, sostituisci `build: .` con `image: ghcr.io/undermix96/lan-scanner:latest` in `docker-compose.yml`.

Build locale senza compose:

```bash
docker build -t lan-scanner .
docker run -d --name lan-scanner --network host --cap-add NET_RAW --cap-add NET_ADMIN -v "$PWD/data:/data" lan-scanner
```

## Configurazione

| Variabile | Default | Descrizione |
|---|---|---|
| `SCAN_TARGETS` | `auto` | `auto` rileva le reti dell'host; altrimenti lista separata da virgole (`192.168.1.0/24,10.0.0.5`) |
| `SCAN_INTERVAL_MINUTES` | `60` | Intervallo tra le scansioni automatiche (`0` = solo manuali) |
| `WEB_PORT` | `8080` | Porta della web UI |
| `NMAP_PORT_ARGS` | `--top-ports 1000 -sV --version-light -T4` | Argomenti nmap per la scansione delle porte (es. `-p- -sV` per tutte le porte) |
| `NMAP_OS_DETECT` | `false` | Abilita il riconoscimento del sistema operativo (`-O`) |
| `NMAP_HOST_TIMEOUT` | `5m` | Tempo massimo per host |
| `DB_PATH` | `/data/lanscanner.db` | Percorso del database SQLite |

Con `SCAN_TARGETS=auto` le reti più grandi di /22 vengono limitate al /24 dell'host, per evitare scansioni enormi.

## API

| Metodo | Endpoint | Descrizione |
|---|---|---|
| GET | `/api/devices` | Dispositivi con porte aperte |
| PATCH | `/api/devices/<id>` | Imposta `alias` / `notes` |
| DELETE | `/api/devices/<id>` | Rimuove un dispositivo dal catalogo |
| GET | `/api/scans` | Ultime scansioni |
| GET | `/api/status` | Stato della scansione in corso |
| POST | `/api/scan` | Avvia una scansione |
| GET | `/api/export.csv` | Esporta il catalogo in CSV |

## Sicurezza

La web UI non ha autenticazione: esponila solo sulla rete locale o dietro un reverse proxy con autenticazione. Scansiona solo reti di cui sei proprietario o per cui hai l'autorizzazione.

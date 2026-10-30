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
docker compose up -d
```

Apri `http://<ip-del-server>:8080`.

> Il container usa `network_mode: host` e le capability `NET_RAW`/`NET_ADMIN`: servono per vedere la LAN direttamente (ARP, MAC address, vendor). Funziona su Linux; su Docker Desktop (macOS/Windows) la rete host non è la LAN reale, quindi imposta `SCAN_TARGETS` manualmente e aspettati di non vedere i MAC.

Il compose usa l'immagine precompilata (amd64 e arm64, es. Raspberry Pi) pubblicata da GitHub Actions su GitHub Container Registry. Per aggiornarla: `docker compose pull && docker compose up -d`.

Senza compose:

```bash
docker run -d --name lan-scanner --network host --cap-add NET_RAW --cap-add NET_ADMIN -v lan-scanner-data:/data ghcr.io/undermix96/lan-scanner:latest
```

Build locale senza compose:

```bash
docker build -t lan-scanner .
docker run -d --name lan-scanner --network host --cap-add NET_RAW --cap-add NET_ADMIN -v lan-scanner-data:/data lan-scanner
```

## Configurazione

Le variabili si possono impostare in due modi:

- **File `.env`** (consigliato): copia l'esempio e modificalo, compose lo legge in automatico.

  ```bash
  cp .env.example .env
  docker compose up -d
  ```

- **Direttamente nel `docker-compose.yml`**, sostituendo il valore nella sezione `environment`.

Le variabili non impostate usano il default indicato sotto. Con `docker run` puoi usare lo stesso file: `docker run --env-file .env ...`.

| Variabile | Default | Descrizione |
|---|---|---|
| `SCAN_TARGETS` | `auto` | `auto` rileva le reti dell'host; altrimenti lista separata da virgole (`192.168.1.0/24,10.0.0.5`) |
| `SCAN_INTERVAL_MINUTES` | `60` | Intervallo tra le scansioni automatiche (`0` = solo manuali) |
| `WEB_PORT` | `8080` | Porta della web UI |
| `NMAP_PORT_ARGS` | `--top-ports 1000 -sV --version-light -T4` | Argomenti nmap per la scansione delle porte (es. `-p- -sV` per tutte le porte) |
| `NMAP_OS_DETECT` | `false` | Abilita il riconoscimento del sistema operativo (`-O`) |
| `NMAP_HOST_TIMEOUT` | `5m` | Tempo massimo per host |
| `DB_PATH` | `/data/lanscanner.db` | Percorso del database SQLite |

Il database è salvato nel volume Docker `lan-scanner-data` (compose lo crea come `<progetto>_lan-scanner-data`, es. `lan-scanner_lan-scanner-data`). Per farne un backup:

```bash
docker run --rm -v lan-scanner_lan-scanner-data:/data -v "$PWD:/backup" alpine cp /data/lanscanner.db /backup/
```

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

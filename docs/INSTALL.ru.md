# Установка

[English](INSTALL.md) · **Русский**

Требования: Debian 13, Python 3.10+, `python3-cryptography`, systemd, публичный
IPv4. Порты: UDP/TCP 53, TCP 443/8443. Дополнительный DNS: UDP/TCP 1053.

## Подготовка

В каталоге исходников релиза на машине подготовки:

```bash
sudo apt-get install python3-cryptography
python3 generate_server_certificates.py --out _private/pki
python3 deployment/export_vps_bundle.py \
  --out _private/vps-ready \
  --public-ip 203.0.113.10 \
  --public \
  --cert _private/pki/cloud-fullchain.pem \
  --key _private/pki/cloud.key
```

Замените пример IPv4. Генератор создаёт закрытые ключи и экспериментальную
цепочку, а не общедоверенный сертификат. Новые материалы требуют проверки
клиентом OFW. Зафиксированный результат OFW получен с цепочкой оператора;
рабочие закрытые ключи не распространяются.

При NAT провайдера добавьте `--bind-ip АДРЕС_ИНТЕРФЕЙСА`. Для ограниченного
доступа замените `--public` повторяемыми `--client ВНЕШНИЙ_IP_ИГРОКА/32`.
Для переноса почты добавьте `--database /путь/cloud.sqlite3`; используется
SQLite backup. Комплект содержит приватные данные и не публикуется.

## Установка на VPS

```bash
scp -r _private/vps-ready root@203.0.113.10:/root/ds2-private
ssh root@203.0.113.10
cd /root/ds2-private
sh deployment/install.sh
```

Установщик создаёт `ds2-server`, размещает код, конфигурацию и TLS-файлы,
включает службу и таймер копий. Существующие конфигурация/база сохраняются;
предлагаемая конфигурация записывается как `config.json.new`. Код и TLS-файлы
при переустановке заменяются. Перед обновлением сохраните текущую установку.

Откройте порты в firewall ОС и провайдера. Установщик firewall не меняет.
Конфликты портов проверяйте через `ss -lntup`.

## Конфигурация и пути

[Публичная](../deployment/config.public.example.json) ·
[Ограниченная](../deployment/config.example.json)

`public_mode:true` требует подписанные билеты и игнорирует список IP.
Ограниченный режим требует `allowed_clients`; сохраняйте
`verify_psn_tickets:true`. Используйте `capture_raw:false`.
Сырые захваты в публичном режиме запрещены. Пути сертификатов считаются
от файла конфигурации. GDS API не реализован.

| Путь | Содержимое |
| --- | --- |
| `/opt/darksiders2-server` | Код и публичные материалы проверки |
| `/etc/darksiders2-server/config.json` | Рабочая конфигурация |
| `/etc/darksiders2-server/pki` | TLS-цепочка и закрытый ключ |
| `/var/lib/darksiders2-server/cloud.sqlite3` | Почта и связи аккаунт/профиль |
| `/var/lib/darksiders2-server/logs` | Ротируемые журналы метаданных |
| `/var/lib/darksiders2-server/backups` | Снимки SQLite, сохраняются последние 14 |

## Проверка

```bash
python3 /opt/darksiders2-server/ds2_server.py --config /etc/darksiders2-server/config.json --check
systemctl status darksiders2-server --no-pager
journalctl -u darksiders2-server -n 50 --no-pager
curl --insecure https://203.0.113.10:8443/health
systemctl list-timers darksiders2-backup.timer
```

Health подтверждает доступность службы; `--insecure` не проверяет принятие
TLS игрой. Постоянное поле `ofw_verified:false` не является проверкой
совместимости. Почту проверяйте по [инструкции игрока](PLAYER-GUIDE.ru.md).
Оба участника должны использовать один сервер. Сохраните рабочий VPN-маршрут
PSN, если он нужен. Замена игрового файла и установка CA на консоль не входят
в процедуру подключения.

## Диагностика

| Результат | Проверить |
| --- | --- |
| Нет DNS-событий | DNS консоли, firewall, маршрут; список IP в ограниченном режиме |
| DNS есть, TCP нет | TCP 8443, шлюз, VPN и обработку имени узла |
| TLS alert 46 | Сертификат отвергнут; записать цепочку и точные версии OFW/игры |
| HTTP 403 | Формат/подпись/срок билета, сервис, сеанс PSN, часы VPS |
| HTTP 503 | Операцию/документ, права, квоты, формат пакета |

Не отключайте публичную авторизацию для диагностики. Ошибки GDS, новостей
и THQ/SSO рассматриваются отдельно от почтового API.

Для существующего VPN-шлюза на ПК `vps_bridge.py` может передавать TLS
без изменений. `configure_vps_direct.py --mode plan` описывает узкий маршрут
для существующей схемы `ps3-vpn.service`; это не универсальный установщик VPN.
Перед применением проверьте план. При обычном подключении помощники не нужны.

## Копии и восстановление

```bash
systemctl start darksiders2-backup.service
journalctl -u darksiders2-backup.service -n 20 --no-pager
```

Для восстановления остановите службу, сохраните согласованный текущий снимок,
установите выбранную базу с владельцем `ds2-server:ds2-server` и режимом `0600`,
запустите службу. Не заменяйте работающую базу SQLite.
Для остановки сервера верните обычные DNS консоли и выполните:

```bash
systemctl disable --now darksiders2-server darksiders2-backup.timer
```

Чувствительные параметры скрываются в журналах; IP и имена конечных точек
остаются. База и копии содержат данные игроков. Файловые журналы ротируются
по 5 МиБ, всего четыре файла; systemd journal имеет отдельный срок хранения.
[Ограничения доступа](PUBLIC-SERVER.ru.md).

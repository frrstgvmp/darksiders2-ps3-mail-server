# Публикация релиза GitHub

[English](PUBLISHING.md) · **Русский**

- Аккаунт: `frrstgvmp`
- Репозиторий: `darksiders2-ps3-mail-server`
- Тег кандидата: `v0.4.6`
- Название релиза: `v0.4.6 — PS3 OFW mailbox server`
- Лицензия: MIT; сторонние материалы описаны в NOTICE.

Описание репозитория:

> Darksiders II PS3 mailbox server for OFW: DNS redirection, PSN ticket verification and persistent gift storage.

Темы: `darksiders-ii`, `ps3`, `ofw`, `game-preservation`, `private-server`, `python`, `sqlite`.

## Исходники

```bash
python3 -m unittest discover -s tests -v
python3 deployment/export_public_source.py --out dist/darksiders2-ps3-mail-server-v0.4.6
cd dist/darksiders2-ps3-mail-server-v0.4.6
git init -b main
git add .
git diff --cached --stat
```

Экспортируется только явный список публичных файлов. Публикуйте этот каталог,
а не исследовательскую папку или приватный комплект VPS. Сохраните LICENSE
и NOTICE. Перед коммитом настройте автора Git; для сокрытия личного адреса
используйте noreply-адрес, указанный GitHub в настройках аккаунта.

## Репозиторий

Создайте пустой публичный `darksiders2-ps3-mail-server` в аккаунте `frrstgvmp`.
Не добавляйте второй README или лицензию. После просмотра файлов:

```bash
git commit -m "Prepare v0.4.6 source release"
git remote add origin https://github.com/frrstgvmp/darksiders2-ps3-mail-server.git
git push -u origin main
```

Авторизуйтесь штатным способом GitHub: браузер, SSH либо менеджер учётных
данных. Пароли/токены не вставляются в URL и файлы.
[Инструкция GitHub](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github).

## Релиз

Создайте черновик релиза по проверенному коммиту `main`, тег `v0.4.6`.
Используйте [английский текст](RELEASE-v0.4.6.md) или [русский](RELEASE-v0.4.6.ru.md).
Начальный релиз отметьте как pre-release, пока независимая установка
и дополнительные издания OFW не проверены. Приложите:

- `darksiders2-ps3-mail-server-v0.4.6.tar.gz`
- `darksiders2-ps3-mail-server-v0.4.6.manifest.json`
- `SHA256SUMS-v0.4.6.txt`

Манифест содержит хеши файлов и переносимые имена артефактов. Рабочие ключи,
билеты, данные игроков, захваты и игровые бинарники исключены.
Перед публикацией проверьте черновик и вложения.
[Инструкция по релизам GitHub](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

## Формулировки совместимости

Указывайте только зафиксированные результаты OFW. Неизвестные версии
прошивки/обновления остаются неизвестными. Реализация японского документа
не является подтверждением японской OFW. Согласовывайте README, совместимость
и статус. Одобрение PSNProfiles не получено; публикация исходников его не заменяет.

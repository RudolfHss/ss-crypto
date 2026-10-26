# OKX számlakapcsolat GitHub Actionsből

Kézzel indítható, csak olvasó hitelesítési teszt. Nem kereskedő bot és nem folyamatos szolgáltatás. A meglévő piaci adatgyűjtőktől független.

## Beállítás

A repó Settings → Secrets and variables → Actions → New repository secret oldalán hozd létre:

| Név | Tartalom |
| --- | --- |
| OKX_API_KEY | Az új API key |
| OKX_SECRET_KEY | A hozzá tartozó secret key |
| OKX_PASSPHRASE | Az API-kulcs létrehozásakor választott passphrase |

Kulcsot ne írj forráskódba, workflow-inputba, issue-ba vagy chatbe. A korábban chatbe bemásolt kulcsot vond vissza. Az új három érték ugyanahhoz a kulcshoz tartozzon. Ne adj Withdraw jogosultságot. Az ellenőrzéshez Read elegendő; egy későbbi kereskedési modul Trade jogosultságot is igényel.

Actions → OKX connection check (read only) → Run workflow. A kulcs típusának megfelelő demo vagy live módot válaszd. A demo külön demókulcsot igényel; a program nem próbál más környezetet, ha a hitelesítés hibás. Mindkét mód kizárólag GET kéréseket küld.

Régió: my.okx.com fiókhoz eea; app.okx.com fiókhoz us; egyéb globális fiókhoz global. Ne a pillanatnyi tartózkodási hely alapján válassz.

## Mit igazol a zöld futás?

Az OKX szerverideje lekérhető, az aláírt számlakonfiguráció-lekérés sikeres. Nem igazol kereskedési jogosultságot, egyenleget, elérhető termékeket vagy végrehajtható megbízást. A napló nem közöl számlaazonosítót, egyenleget vagy teljes API-választ. Nincs artifact vagy számlaadat-commit.

Hibánál a futás megbukik: nincs automatikus demó/éles váltás vagy újrapróbált megbízás. A szkript csak public/time és account/config GET végpontot enged. A hitelesített kérések átirányítását elutasítja.

## GitHub futtatási korlátok

A standard GitHub-hosted runner kimenő IP-je változhat. Ha az OKX-kulcs fix IP-re korlátozott, használj megfelelő, rögzített kimenő IP-jű futtatót; ne távolítsd el automatikusan az IP-korlátot. GitHub Actions kézi és időzített feladatokra alkalmas, nem folyamatos, kis késleltetésű scalp végrehajtásra.

## Következő lépés

Sikeres kapcsolatteszt után külön kell meghatározni a próbaügyletet: demó/éles, instrumentum, spot/futures, vétel/eladás, mennyiség, limitár vagy piaci típus, szükség esetén stop és tőkeáttétel. Ebben a modulban nincs megbízásküldés, automatizált stratégia vagy kiutalás.

Forrás: https://www.okx.com/docs-v5/ (REST authentication, regional API domains, demo trading).

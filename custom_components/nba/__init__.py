"""Intégration NBA pour Home Assistant."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import NBACoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

BLUEPRINT_FILE = "nba_game_notification.yaml"


def _install_blueprint(config_dir: str, component_dir: Path) -> None:
    """Copie le blueprint fourni vers /config/blueprints/automation/nba/.

    - ne fait rien si le fichier source est absent ;
    - crée le fichier s'il n'existe pas ;
    - n'écrase jamais un fichier déjà présent, afin de respecter
      d'éventuelles modifications de l'utilisateur. Pour récupérer une
      nouvelle version, il suffit de supprimer l'ancien fichier puis
      de redémarrer Home Assistant.
    """
    source = component_dir / "blueprints" / "automation" / BLUEPRINT_FILE
    if not source.is_file():
        return

    target_dir = Path(config_dir) / "blueprints" / "automation" / "nba"
    target = target_dir / BLUEPRINT_FILE

    if target.exists():
        # Mise à jour uniquement si le fichier installé est identique à une
        # ancienne copie non modifiée par l'utilisateur (marqueur ci-dessous).
        try:
            installed = target.read_text(encoding="utf-8")
            new = source.read_text(encoding="utf-8")
        except OSError:
            return
        if installed == new or not installed.startswith("# nba-auto-managed"):
            return
        target.write_text(new, encoding="utf-8")
        _LOGGER.info("Blueprint NBA mis à jour : %s", target)
        return

    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    _LOGGER.info("Blueprint NBA installé : %s", target)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Démarre l'intégration depuis une entrée de configuration."""
    # Installation du blueprint (opération disque : hors boucle principale)
    try:
        await hass.async_add_executor_job(
            _install_blueprint, hass.config.config_dir, Path(__file__).parent
        )
    except Exception:  # noqa: BLE001 - ne doit jamais bloquer l'intégration
        _LOGGER.warning("Impossible d'installer le blueprint NBA", exc_info=True)

    coordinator = NBACoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Arrête l'intégration."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return ok

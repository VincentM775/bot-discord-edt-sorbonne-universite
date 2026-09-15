Il reste une commande à lancer toi-même (sudo, je ne peux pas), pour qu'il démarre au
  boot même sans que tu ouvres ta session — sinon il ne démarre qu'à ta connexion et
  s'arrête quand tu te déconnectes :

  ! sudo loginctl enable-linger vmatias

  Les commandes utiles au quotidien

  systemctl --user status bot-edt      # état
  systemctl --user restart bot-edt     # après une modif du code ou du .env
  systemctl --user stop bot-edt        # arrêter
  journalctl --user -u bot-edt -f      # logs en direct

  ⚠️  Ne lance plus python bot.py à la main : tu aurais deux bots en parallèle et chaque
  message serait posté en double.

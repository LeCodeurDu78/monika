# Emplacement de l'avatar 3D animé

Ce dossier est l'emplacement prévu pour le futur modèle 3D animé de Monika.

## Comment le brancher

1. Déposer ici le fichier exporté (nommé exactement `monika.glb`, ou `monika.gltf`
   si export non-binaire avec ses textures à côté).
2. Rafraîchir le dashboard : `/api/status` détecte automatiquement le fichier
   (`avatar.model_available`) et l'affiche dans `avatar-caption`.
3. Compléter le rendu dans `dashboard/static/js/app.js`, fonction `updateAvatar()` :
   charger Three.js + `GLTFLoader`, instancier un renderer sur `#avatar-canvas`,
   charger `/static/avatar/monika.glb`, lancer la boucle d'animation (mixer
   d'animations Three.js si le modèle a des clips).

En attendant, le dashboard affiche un placeholder animé (l'orbe qui "respire").

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const MODEL_URL = "/model.glb";
const POLL_INTERVAL_MS = 100;
const JAW_MAX_ANGLE = 0.30;          // radians, ouverture max de la mâchoire
const JAW_BONE_NAMES = ["CC_Base_JawRoot", "CC_Base_UpperJaw"];
const HEAD_BONE_NAME = "CC_Base_Head";
const EYE_BONE_NAMES = ["CC_Base_L_Eye", "CC_Base_R_Eye"];

const AURA_COLORS = {
    idle: 0x6ee7ff,
    listening: 0x7dd3fc,
    thinking: 0xc4b5fd,
    speaking: 0xfb7185,
};
const STATUS_LABELS = {
    idle: "Au repos",
    listening: "Je t'écoute",
    thinking: "Je réfléchis",
    speaking: "Je parle",
};

// Quel clip (bakée dans model.glb par utils/add_animations.py) jouer pour
// chaque état. Un état sans mocap dédié retombe sur "Idle" — il suffit
// d'ajouter une entrée ici le jour où une nouvelle animation est bakée
// (ex. "speaking": "Talking" une fois Talking.fbx ajouté au modèle).
const STATE_CLIPS = {
    idle: "Idle",
    listening: "Idle",
    thinking: "Thinking",
    speaking: "Idle",
};
const ANIMATION_CROSSFADE_SECONDS = 0.35;

let jawSign = parseFloat(localStorage.getItem("monika_jaw_sign") || "1");

// ---------------------------------------------------------------------------
// Scene setup
// ---------------------------------------------------------------------------
const holder = document.getElementById("canvas-holder");
const scene = new THREE.Scene();

const camera = new THREE.PerspectiveCamera(32, window.innerWidth / window.innerHeight, 0.05, 50);
camera.position.set(0, 1.55, 1.35);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
holder.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.target.set(0, 1.45, 0);
controls.enableDamping = true;
controls.dampingFactor = 0.08;
controls.minDistance = 0.6;
controls.maxDistance = 2.6;
controls.maxPolarAngle = Math.PI * 0.62;
controls.minPolarAngle = Math.PI * 0.25;
controls.enablePan = false;
controls.update();

// Lighting: douce, façon "webcam overlay" plutôt que rendu réaliste dur.
scene.add(new THREE.AmbientLight(0xffffff, 0.9));

const keyLight = new THREE.DirectionalLight(0xfff2e6, 1.1);
keyLight.position.set(1.2, 2.2, 1.6);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight(0x8ab4ff, 0.6);
rimLight.position.set(-1.5, 1.6, -1.2);
scene.add(rimLight);

const auraLight = new THREE.PointLight(AURA_COLORS.idle, 1.2, 3.0);
auraLight.position.set(0, 1.1, 0.6);
scene.add(auraLight);

// ---------------------------------------------------------------------------
// Load the model
// ---------------------------------------------------------------------------
const bones = {};        // name -> THREE.Bone
const boneBase = {};     // name -> { rotation: Euler, scale: Vector3 } d'origine
const eyeMeshes = [];    // meshes à "cligner"

let jawBone = null;
let headBone = null;
let loadedModel = null;
let faceSign = parseFloat(localStorage.getItem("monika_face_sign") || "1");

let mixer = null;              // THREE.AnimationMixer, créé une fois le modèle chargé
const actions = {};            // nom de clip ("Idle", "Thinking", ...) -> THREE.AnimationAction
let activeAction = null;

function findBone(root, name) {
    let found = null;
    root.traverse((obj) => {
        if (!found && obj.isBone && obj.name === name) found = obj;
    });
    return found;
}

function rememberBase(bone) {
    boneBase[bone.name] = {
        rotation: bone.rotation.clone(),
        scale: bone.scale.clone(),
    };
}

function frameCamera(model) {
    // 1. Force Three.js à calculer la position spatiale exacte des os
    // avant même le premier rendu
    model.updateMatrixWorld(true);

    const box = new THREE.Box3().setFromObject(model);
    const center = new THREE.Vector3();
    box.getCenter(center); // On garde ça pour centrer sur l'axe X et Z

    let eyeLevelY = 1.55;
    let bustTargetY = 1.35;

    // 2. Si on a trouvé la tête, on se cale dessus !
    if (headBone) {
        const headPos = new THREE.Vector3();
        headBone.getWorldPosition(headPos);

        eyeLevelY = headPos.y;           // Hauteur de la caméra = hauteur des yeux
        bustTargetY = headPos.y - 0.25;  // Cible de la caméra = 25 cm sous la tête (le buste)
    } else {
        // Solution de secours au cas où l'os n'est pas détecté
        eyeLevelY = box.min.y + 1.7 * 0.85;
        bustTargetY = box.min.y + 1.7 * 0.65;
    }

    // 3. Placement de la caméra
    const camDistance = 1.2; // Distance de recul
    camera.position.set(center.x, eyeLevelY, center.z + camDistance * faceSign);
    camera.near = 0.05;
    camera.far = 50;
    camera.updateProjectionMatrix();

    // 4. Orientation de la caméra vers le buste
    controls.target.set(center.x, bustTargetY, center.z);
    controls.minDistance = 0.2;
    controls.maxDistance = 5.0; // Autorise à dézoomer
    controls.update();

    // 5. Ajustement de la lumière d'aura sur le buste
    auraLight.position.set(center.x, bustTargetY, center.z + 0.3 * faceSign);
    auraLight.distance = 3.0;
}

const loader = new GLTFLoader();
loader.load(
    MODEL_URL,
    (gltf) => {
        const model = gltf.scene;
        model.position.set(0, 0, 0);
        scene.add(model);

        // Repère les os utiles. On tolère leur absence (on anime juste ce qui existe).
        for (const name of JAW_BONE_NAMES) {
            const b = findBone(model, name);
            if (b) { bones[name] = b; rememberBase(b); if (!jawBone) jawBone = b; }
        }
        headBone = findBone(model, HEAD_BONE_NAME);
        for (const name of EYE_BONE_NAMES) {
            const b = findBone(model, name);
            if (b) { bones[name] = b; rememberBase(b); }
        }

        // Repère les meshes des yeux (pour le clignement) en excluant sourcils/cils.
        model.traverse((obj) => {
            if (obj.isMesh || obj.isSkinnedMesh) {
                const n = obj.name.toLowerCase();
                if (n.includes("eyes")) eyeMeshes.push(obj);
            }
        });

        loadedModel = model;
        frameCamera(model);
        setupAnimations(model, gltf.animations);

        document.getElementById("loading").style.display = "none";
    },
    undefined,
    (err) => {
        console.error("Erreur de chargement du modèle :", err);
        document.getElementById("loading").textContent =
            "Impossible de charger model.glb (voir la console).";
    }
);

// ---------------------------------------------------------------------------
// Animation clips (Idle / Thinking, bakées dans model.glb par
// utils/add_animations.py) — remplace les mouvements procéduraux qui
// servaient de repère avant d'avoir du vrai mocap.
// ---------------------------------------------------------------------------
function setupAnimations(model, clips) {
    mixer = new THREE.AnimationMixer(model);
    for (const clip of clips) {
        const action = mixer.clipAction(clip);
        action.setEffectiveWeight(0);
        action.play();               // actif dès le départ, mais à poids nul tant qu'il n'est pas sélectionné
        actions[clip.name] = action;
    }
    if (Object.keys(actions).length === 0) {
        console.warn("Aucune animation dans model.glb — avez-vous lancé utils/add_animations.py ?");
        return;
    }
    activeAction = null;
    playStateAnimation(currentState, 0); // pose initiale, sans fondu (sinon flash en pose de repos)
}

function playStateAnimation(state, fadeSeconds = ANIMATION_CROSSFADE_SECONDS) {
    if (!mixer) return; // modèle pas encore chargé ; setupAnimations() rejouera l'état courant
    const wanted = STATE_CLIPS[state] || "Idle";
    const next = actions[wanted] || actions.Idle;
    if (!next || next === activeAction) return;

    const previous = activeAction;
    activeAction = next;

    next.reset().setEffectiveTimeScale(1).setEffectiveWeight(1).fadeIn(fadeSeconds).play();
    if (previous) previous.fadeOut(fadeSeconds);
}

// ---------------------------------------------------------------------------
// State polling (idle / listening / thinking / speaking + amplitude)
// ---------------------------------------------------------------------------
let currentState = "idle";
let targetAmplitude = 0;
let smoothedAmplitude = 0;

async function pollState() {
    try {
        const res = await fetch("/api/state", { cache: "no-store" });
        if (res.ok) {
            const data = await res.json();
            if (data.state !== currentState) applyState(data.state);
            targetAmplitude = data.amplitude ?? 0;
        }
    } catch (e) {
        // Le serveur peut ne pas être encore prêt au tout début ; on réessaie simplement.
    } finally {
        setTimeout(pollState, POLL_INTERVAL_MS);
    }
}

function applyState(state) {
    currentState = state;
    playStateAnimation(state);
    const color = AURA_COLORS[state] ?? AURA_COLORS.idle;
    document.getElementById("status-dot").style.background = `#${color.toString(16).padStart(6, "0")}`;
    document.getElementById("status-dot").style.boxShadow = `0 0 12px 3px #${color.toString(16).padStart(6, "0")}`;
    document.getElementById("status-label").textContent = STATUS_LABELS[state] ?? state;
}

pollState();

// ---------------------------------------------------------------------------
// Blink (fake : on pince l'échelle Y des meshes "yeux" brièvement)
// ---------------------------------------------------------------------------
let nextBlinkAt = performance.now() + 2000;
let blinkPhase = 0; // 0 = ouvert, en cours d'animation sinon

function updateBlink(now) {
    if (eyeMeshes.length === 0) return;

    if (blinkPhase === 0 && now >= nextBlinkAt) {
        blinkPhase = { start: now, duration: 110 };
        nextBlinkAt = now + 2600 + Math.random() * 3200;
    }
    if (typeof blinkPhase === "object") {
        const t = (now - blinkPhase.start) / blinkPhase.duration;
        if (t >= 1) {
            for (const m of eyeMeshes) m.scale.y = 1;
            blinkPhase = 0;
        } else {
            // triangle 0->1->0 pour un clignement rapide aller-retour
            const k = t < 0.5 ? t * 2 : (1 - t) * 2;
            const scaleY = 1 - k * 0.92;
            for (const m of eyeMeshes) m.scale.y = scaleY;
        }
    }
}

// ---------------------------------------------------------------------------
// Animation loop
// ---------------------------------------------------------------------------
const clock = new THREE.Clock();
let elapsedTime = 0; // cumulé à la main (voir animate) pour n'appeler clock.getDelta() qu'une fois par frame
const mouse = { x: 0, y: 0 };
window.addEventListener("pointermove", (e) => {
    mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
    mouse.y = (e.clientY / window.innerHeight) * 2 - 1;
});

function animate() {
    requestAnimationFrame(animate);
    const delta = clock.getDelta();
    elapsedTime += delta;
    const t = elapsedTime;
    const now = performance.now();

    // Amplitude lissée (les mises à jour serveur arrivent à ~10 Hz, on interpole
    // à 60 Hz pour un mouvement de bouche fluide).
    smoothedAmplitude += (targetAmplitude - smoothedAmplitude) * 0.35;

    // Corps entier (colonne, bras, jambes, tête...) : piloté par le clip mocap
    // actif (Idle/Thinking — voir setupAnimations/playStateAnimation). Tout ce
    // qui suit vient s'AJOUTER par-dessus la pose que le mixer vient de poser,
    // jamais la remplacer, sous peine d'effacer l'animation.
    if (mixer) mixer.update(delta);

    // Regard de la tête vers la souris + micro-mouvement en parlant : couche
    // additive sur la pose animée du frame courant (le mocap a déjà fourni le
    // "base.rotation" de ce frame, on ne fait qu'y ajouter un petit delta).
    if (headBone) {
        const lookX = mouse.y * 0.06;
        const lookY = mouse.x * 0.10;
        const bob = currentState === "speaking" ? Math.sin(t * 2.2) * 0.01 : 0;
        headBone.rotation.x += lookX + bob;
        headBone.rotation.y += lookY;
    }

    // Regard des yeux : bones absents du squelette Mixamo, donc jamais
    // touchés par le mixer — pas de conflit à gérer ici.
    for (const name of EYE_BONE_NAMES) {
        const bone = bones[name];
        if (!bone) continue;
        const base = boneBase[name];
        bone.rotation.y = base.rotation.y + mouse.x * 0.05;
        bone.rotation.x = base.rotation.x + mouse.y * 0.03;
    }

    // Mâchoire : suit l'amplitude audio quand Monika parle, sinon reste fermée.
    const jawTarget = currentState === "speaking" ? smoothedAmplitude : 0;
    for (const name of JAW_BONE_NAMES) {
        const bone = bones[name];
        if (!bone) continue;
        const base = boneBase[name];
        bone.rotation.x = base.rotation.x + jawSign * jawTarget * JAW_MAX_ANGLE;
    }

    updateBlink(now);

    // Aura : couleur + pulsation légère selon l'état.
    const color = AURA_COLORS[currentState] ?? AURA_COLORS.idle;
    auraLight.color.setHex(color);
    auraLight.intensity = 1.0 + (currentState === "speaking" ? smoothedAmplitude * 0.8 : Math.sin(t * 1.4) * 0.15);

    controls.update();
    renderer.render(scene, camera);
}
animate();

// ---------------------------------------------------------------------------
// Divers
// ---------------------------------------------------------------------------
window.addEventListener("resize", () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});
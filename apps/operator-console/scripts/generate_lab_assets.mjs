/**
 * Procedural PBR 3D asset generator for Industrial Reliability Virtual Lab.
 * Generates deterministic GLB binary models and catalog manifest.
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
// Polyfill FileReader for GLTFExporter in Node before importing Three.js modules
if (typeof globalThis.FileReader === 'undefined') {
  globalThis.FileReader = class FileReader {
    readAsArrayBuffer(blob) {
      blob.arrayBuffer().then((buf) => {
        this.result = buf;
        if (this.onload) this.onload({ target: this });
        if (this.onloadend) this.onloadend({ target: this });
      });
    }
    readAsDataURL(blob) {
      blob.arrayBuffer().then((buf) => {
        const base64 = Buffer.from(buf).toString('base64');
        this.result = `data:${blob.type || 'application/octet-stream'};base64,${base64}`;
        if (this.onload) this.onload({ target: this });
        if (this.onloadend) this.onloadend({ target: this });
      });
    }
  };
}

const THREE = await import('three');
const { GLTFExporter } = await import('three/examples/jsm/exporters/GLTFExporter.js');

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PUBLIC_DIR = path.resolve(__dirname, '../public/lab-assets');
// Shared PBR Materials
const enamelMat = new THREE.MeshStandardMaterial({
  color: 0x315b70,
  roughness: 0.35,
  metalness: 0.3,
  name: 'MachineEnamel',
});

const metalMat = new THREE.MeshStandardMaterial({
  color: 0x89949f,
  roughness: 0.25,
  metalness: 0.8,
  name: 'IndustrialMetal',
});

const rubberMat = new THREE.MeshStandardMaterial({
  color: 0x20262d,
  roughness: 0.85,
  metalness: 0.1,
  name: 'GasketRubber',
});

const brassMat = new THREE.MeshStandardMaterial({
  color: 0xb58934,
  roughness: 0.3,
  metalness: 0.7,
  name: 'BrassFitting',
});

const accentYellowMat = new THREE.MeshStandardMaterial({
  color: 0xd4a017,
  roughness: 0.45,
  metalness: 0.2,
  name: 'SafetyYellow',
});

const dialFaceMat = new THREE.MeshStandardMaterial({
  color: 0xf5f7f8,
  roughness: 0.6,
  metalness: 0.1,
  name: 'DialFace',
});

const indicatorRedMat = new THREE.MeshStandardMaterial({
  color: 0xc0392b,
  roughness: 0.3,
  metalness: 0.2,
  name: 'IndicatorRed',
});

const glassMat = new THREE.MeshStandardMaterial({
  color: 0xeaf2f8,
  roughness: 0.1,
  metalness: 0.1,
  transparent: true,
  opacity: 0.7,
  name: 'GaugeGlass',
});

// Helper for exporting three.js scene to GLB Buffer
function exportToGLB(scene) {
  return new Promise((resolve, reject) => {
    const exporter = new GLTFExporter();
    exporter.parse(
      scene,
      (gltf) => {
        resolve(Buffer.from(gltf));
      },
      (err) => {
        reject(err);
      },
      { binary: true }
    );
  });
}

// 1. COMPRESSOR
async function buildCompressor() {
  const root = new THREE.Group();
  root.name = 'COMPRESSOR_ROOT';

  // Base skid / feet
  const baseGeom = new THREE.BoxGeometry(1.6, 0.1, 1.0);
  const baseMesh = new THREE.Mesh(baseGeom, metalMat);
  baseMesh.position.set(0, 0.05, 0);
  root.add(baseMesh);

  // Main cabinet / sound enclosure
  const bodyGeom = new THREE.BoxGeometry(1.3, 1.0, 0.85);
  const bodyMesh = new THREE.Mesh(bodyGeom, enamelMat);
  bodyMesh.position.set(-0.05, 0.6, 0);
  root.add(bodyMesh);

  // Motor housing on top rear
  const motorGeom = new THREE.CylinderGeometry(0.2, 0.2, 0.6, 16);
  motorGeom.rotateZ(Math.PI / 2);
  const motorMesh = new THREE.Mesh(motorGeom, metalMat);
  motorMesh.position.set(-0.2, 1.15, -0.15);
  root.add(motorMesh);

  // Fan grille / shroud
  const shroudGeom = new THREE.CylinderGeometry(0.22, 0.22, 0.05, 24);
  shroudGeom.rotateX(Math.PI / 2);
  const shroudMesh = new THREE.Mesh(shroudGeom, metalMat);
  shroudMesh.position.set(0.1, 0.7, 0.43);
  root.add(shroudMesh);

  // Rotor / Fan Blades (animated node)
  const rotor = new THREE.Group();
  rotor.name = 'rotor';
  rotor.position.set(0.1, 0.7, 0.43);
  for (let i = 0; i < 6; i++) {
    const bladeGeom = new THREE.BoxGeometry(0.04, 0.36, 0.01);
    const bladeMesh = new THREE.Mesh(bladeGeom, accentYellowMat);
    bladeMesh.rotation.z = (i * Math.PI) / 3;
    rotor.add(bladeMesh);
  }
  root.add(rotor);

  // Gauge on top
  const gaugeGroup = new THREE.Group();
  gaugeGroup.name = 'gauge';
  gaugeGroup.position.set(0.4, 1.15, 0.2);
  const gaugeStem = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.08, 12), brassMat);
  gaugeStem.position.set(0, 0.04, 0);
  gaugeGroup.add(gaugeStem);

  const dialMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.04, 24), metalMat);
  dialMesh.position.set(0, 0.1, 0);
  gaugeGroup.add(dialMesh);

  const dialFace = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.075, 0.005, 24), dialFaceMat);
  dialFace.position.set(0, 0.122, 0);
  gaugeGroup.add(dialFace);
  root.add(gaugeGroup);

  // Output flange and Port OUT Anchor
  const flangeGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.1, 16);
  flangeGeom.rotateZ(Math.PI / 2);
  const flangeMesh = new THREE.Mesh(flangeGeom, metalMat);
  flangeMesh.position.set(0.75, 0.5, 0.0);
  root.add(flangeMesh);

  const portOut = new THREE.Object3D();
  portOut.name = 'port_OUT';
  portOut.position.set(0.8, 0.5, 0.0);
  root.add(portOut);

  return exportToGLB(root);
}

// 2. TANK
async function buildTank() {
  const root = new THREE.Group();
  root.name = 'TANK_ROOT';

  // 4 Legs
  const legPositions = [
    [-0.32, 0, -0.32],
    [0.32, 0, -0.32],
    [-0.32, 0, 0.32],
    [0.32, 0, 0.32],
  ];
  for (const [lx, , lz] of legPositions) {
    const legGeom = new THREE.CylinderGeometry(0.04, 0.05, 0.35, 12);
    const legMesh = new THREE.Mesh(legGeom, metalMat);
    legMesh.position.set(lx, 0.175, lz);
    root.add(legMesh);
  }

  // Main Cylinder
  const cylGeom = new THREE.CylinderGeometry(0.45, 0.45, 1.4, 32);
  const cylMesh = new THREE.Mesh(cylGeom, enamelMat);
  cylMesh.position.set(0, 1.05, 0);
  root.add(cylMesh);

  // Top Cap (hemisphere)
  const topCapGeom = new THREE.SphereGeometry(0.45, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2);
  const topCapMesh = new THREE.Mesh(topCapGeom, enamelMat);
  topCapMesh.position.set(0, 1.75, 0);
  root.add(topCapMesh);

  // Bottom Cap (hemisphere inverted)
  const botCapGeom = new THREE.SphereGeometry(0.45, 32, 16, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2);
  const botCapMesh = new THREE.Mesh(botCapGeom, enamelMat);
  botCapMesh.position.set(0, 0.35, 0);
  root.add(botCapMesh);

  // Reinforcement weld seam rings
  for (const y of [0.65, 1.45]) {
    const ringGeom = new THREE.TorusGeometry(0.452, 0.015, 8, 32);
    ringGeom.rotateX(Math.PI / 2);
    const ringMesh = new THREE.Mesh(ringGeom, metalMat);
    ringMesh.position.set(0, y, 0);
    root.add(ringMesh);
  }

  // Port A Flange (Left at x = -0.45, y = 0.9, z = 0)
  const flangeAGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.06, 16);
  flangeAGeom.rotateZ(Math.PI / 2);
  const flangeAMesh = new THREE.Mesh(flangeAGeom, metalMat);
  flangeAMesh.position.set(-0.45, 0.9, 0);
  root.add(flangeAMesh);

  const portA = new THREE.Object3D();
  portA.name = 'port_A';
  portA.position.set(-0.45, 0.9, 0);
  root.add(portA);

  // Port B Flange (Right at x = 0.45, y = 0.9, z = 0)
  const flangeBGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.06, 16);
  flangeBGeom.rotateZ(Math.PI / 2);
  const flangeBMesh = new THREE.Mesh(flangeBGeom, metalMat);
  flangeBMesh.position.set(0.45, 0.9, 0);
  root.add(flangeBMesh);

  const portB = new THREE.Object3D();
  portB.name = 'port_B';
  portB.position.set(0.45, 0.9, 0);
  root.add(portB);

  // Top Pressure Relief Valve / Gauge
  const gauge = new THREE.Group();
  gauge.name = 'gauge';
  gauge.position.set(0, 2.2, 0);
  const gMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 0.04, 24), brassMat);
  gauge.add(gMesh);
  root.add(gauge);

  return exportToGLB(root);
}

// 3. ISOLATION VALVE
async function buildIsolationValve() {
  const root = new THREE.Group();
  root.name = 'ISOLATION_VALVE_ROOT';

  // Central body block
  const bodyGeom = new THREE.BoxGeometry(0.2, 0.22, 0.2);
  const bodyMesh = new THREE.Mesh(bodyGeom, metalMat);
  bodyMesh.position.set(0, 0.3, 0);
  root.add(bodyMesh);

  // Pipe stubs and flanges on left & right
  for (const sign of [-1, 1]) {
    const pipeGeom = new THREE.CylinderGeometry(0.05, 0.05, 0.1, 16);
    pipeGeom.rotateZ(Math.PI / 2);
    const pipeMesh = new THREE.Mesh(pipeGeom, metalMat);
    pipeMesh.position.set(sign * 0.12, 0.3, 0);
    root.add(pipeMesh);

    const flgGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.03, 16);
    flgGeom.rotateZ(Math.PI / 2);
    const flgMesh = new THREE.Mesh(flgGeom, metalMat);
    flgMesh.position.set(sign * 0.18, 0.3, 0);
    root.add(flgMesh);
  }

  // Port A Anchor
  const portA = new THREE.Object3D();
  portA.name = 'port_A';
  portA.position.set(-0.2, 0.3, 0);
  root.add(portA);

  // Port B Anchor
  const portB = new THREE.Object3D();
  portB.name = 'port_B';
  portB.position.set(0.2, 0.3, 0);
  root.add(portB);

  // Valve Bonnet / stem
  const bonnetGeom = new THREE.CylinderGeometry(0.04, 0.04, 0.15, 16);
  const bonnetMesh = new THREE.Mesh(bonnetGeom, brassMat);
  bonnetMesh.position.set(0, 0.44, 0);
  root.add(bonnetMesh);

  // Rotatable Handle (node named 'handle')
  const handle = new THREE.Group();
  handle.name = 'handle';
  handle.position.set(0, 0.52, 0);

  const hubMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.02, 16), metalMat);
  handle.add(hubMesh);

  const leverGeom = new THREE.BoxGeometry(0.24, 0.02, 0.04);
  leverGeom.translate(0.1, 0, 0);
  const leverMesh = new THREE.Mesh(leverGeom, indicatorRedMat);
  handle.add(leverMesh);

  root.add(handle);

  return exportToGLB(root);
}

// 4. CONTROL VALVE
async function buildControlValve() {
  const root = new THREE.Group();
  root.name = 'CONTROL_VALVE_ROOT';

  // Central body
  const bodyGeom = new THREE.CylinderGeometry(0.1, 0.1, 0.22, 16);
  const bodyMesh = new THREE.Mesh(bodyGeom, metalMat);
  bodyMesh.position.set(0, 0.3, 0);
  root.add(bodyMesh);

  // Flanges left and right
  for (const sign of [-1, 1]) {
    const flgGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.03, 16);
    flgGeom.rotateZ(Math.PI / 2);
    const flgMesh = new THREE.Mesh(flgGeom, metalMat);
    flgMesh.position.set(sign * 0.18, 0.3, 0);
    root.add(flgMesh);
  }

  // Port A Anchor
  const portA = new THREE.Object3D();
  portA.name = 'port_A';
  portA.position.set(-0.2, 0.3, 0);
  root.add(portA);

  // Port B Anchor
  const portB = new THREE.Object3D();
  portB.name = 'port_B';
  portB.position.set(0.2, 0.3, 0);
  root.add(portB);

  // Yoke / stem column
  const yokeGeom = new THREE.CylinderGeometry(0.03, 0.03, 0.2, 12);
  const yokeMesh = new THREE.Mesh(yokeGeom, metalMat);
  yokeMesh.position.set(0, 0.48, 0);
  root.add(yokeMesh);

  // Diaphragm actuator dome
  const domeGeom = new THREE.CylinderGeometry(0.2, 0.2, 0.14, 24);
  const domeMesh = new THREE.Mesh(domeGeom, enamelMat);
  domeMesh.position.set(0, 0.65, 0);
  root.add(domeMesh);

  const topCapGeom = new THREE.SphereGeometry(0.2, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2);
  const topCapMesh = new THREE.Mesh(topCapGeom, enamelMat);
  topCapMesh.position.set(0, 0.72, 0);
  root.add(topCapMesh);

  // Positioner box on side with moving indicator
  const posBox = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.15, 0.1), metalMat);
  posBox.position.set(0.12, 0.5, 0);
  root.add(posBox);

  // Indicator node
  const indicator = new THREE.Group();
  indicator.name = 'indicator';
  indicator.position.set(0.18, 0.5, 0);
  const pointerMesh = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.06, 0.02), indicatorRedMat);
  indicator.add(pointerMesh);
  root.add(indicator);

  return exportToGLB(root);
}

// 5. DEMAND
async function buildDemand() {
  const root = new THREE.Group();
  root.name = 'DEMAND_ROOT';

  // Base frame
  const frameGeom = new THREE.BoxGeometry(0.8, 0.08, 0.7);
  const frameMesh = new THREE.Mesh(frameGeom, metalMat);
  frameMesh.position.set(0, 0.04, 0);
  root.add(frameMesh);

  // Main cabinet
  const cabGeom = new THREE.BoxGeometry(0.72, 1.0, 0.62);
  const cabMesh = new THREE.Mesh(cabGeom, enamelMat);
  cabMesh.position.set(0, 0.58, 0);
  root.add(cabMesh);

  // Louvers / vents on front
  for (let i = 0; i < 5; i++) {
    const louver = new THREE.Mesh(new THREE.BoxGeometry(0.45, 0.02, 0.01), rubberMat);
    louver.position.set(0, 0.4 + i * 0.08, 0.315);
    root.add(louver);
  }

  // Status indicator panel
  const panelMesh = new THREE.Mesh(new THREE.BoxGeometry(0.25, 0.12, 0.02), metalMat);
  panelMesh.position.set(0, 0.9, 0.315);
  root.add(panelMesh);

  // Port IN Flange on left
  const flangeGeom = new THREE.CylinderGeometry(0.08, 0.08, 0.08, 16);
  flangeGeom.rotateZ(Math.PI / 2);
  const flangeMesh = new THREE.Mesh(flangeGeom, metalMat);
  flangeMesh.position.set(-0.38, 0.6, 0);
  root.add(flangeMesh);

  const portIn = new THREE.Object3D();
  portIn.name = 'port_IN';
  portIn.position.set(-0.4, 0.6, 0);
  root.add(portIn);

  return exportToGLB(root);
}

// 6. PRESSURE SENSOR
async function buildPressureSensor() {
  const root = new THREE.Group();
  root.name = 'PRESSURE_SENSOR_ROOT';

  // Mounting stem
  const stemGeom = new THREE.CylinderGeometry(0.018, 0.018, 0.08, 12);
  const stemMesh = new THREE.Mesh(stemGeom, brassMat);
  stemMesh.position.set(0, 0.04, 0);
  root.add(stemMesh);

  // Dial Body
  const dialBodyGeom = new THREE.CylinderGeometry(0.06, 0.06, 0.035, 24);
  dialBodyGeom.rotateX(Math.PI / 2);
  const dialBodyMesh = new THREE.Mesh(dialBodyGeom, metalMat);
  dialBodyMesh.position.set(0, 0.13, 0);
  root.add(dialBodyMesh);

  // Dial Face
  const faceGeom = new THREE.CircleGeometry(0.055, 24);
  const faceMesh = new THREE.Mesh(faceGeom, dialFaceMat);
  faceMesh.position.set(0, 0.13, 0.018);
  root.add(faceMesh);

  // Needle node
  const needle = new THREE.Group();
  needle.name = 'needle';
  needle.position.set(0, 0.13, 0.02);
  const needleGeom = new THREE.BoxGeometry(0.003, 0.045, 0.002);
  needleGeom.translate(0, 0.02, 0);
  const needleMesh = new THREE.Mesh(needleGeom, indicatorRedMat);
  needle.add(needleMesh);
  root.add(needle);

  // Protective Glass
  const glassGeom = new THREE.CircleGeometry(0.056, 24);
  const gMesh = new THREE.Mesh(glassGeom, glassMat);
  gMesh.position.set(0, 0.13, 0.022);
  root.add(gMesh);

  // Anchor
  const anchor = new THREE.Object3D();
  anchor.name = 'sensor_anchor';
  anchor.position.set(0, 0, 0);
  root.add(anchor);

  return exportToGLB(root);
}

// 7. FLOW SENSOR
async function buildFlowSensor() {
  const root = new THREE.Group();
  root.name = 'FLOW_SENSOR_ROOT';

  // Inline pipe section
  const pipeGeom = new THREE.CylinderGeometry(0.04, 0.04, 0.22, 16);
  pipeGeom.rotateZ(Math.PI / 2);
  const pipeMesh = new THREE.Mesh(pipeGeom, metalMat);
  pipeMesh.position.set(0, 0.1, 0);
  root.add(pipeMesh);

  // Flanges left and right
  for (const sign of [-1, 1]) {
    const flg = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.02, 16), metalMat);
    flg.geometry.rotateZ(Math.PI / 2);
    flg.position.set(sign * 0.1, 0.1, 0);
    root.add(flg);
  }

  // Transmitter neck and housing
  const neckGeom = new THREE.CylinderGeometry(0.02, 0.02, 0.06, 12);
  const neckMesh = new THREE.Mesh(neckGeom, metalMat);
  neckMesh.position.set(0, 0.16, 0);
  root.add(neckMesh);

  const headGeom = new THREE.BoxGeometry(0.1, 0.1, 0.08);
  const headMesh = new THREE.Mesh(headGeom, enamelMat);
  headMesh.position.set(0, 0.23, 0);
  root.add(headMesh);

  // Digital display glass
  const displayGeom = new THREE.BoxGeometry(0.07, 0.04, 0.005);
  const displayMesh = new THREE.Mesh(displayGeom, glassMat);
  displayMesh.position.set(0, 0.23, 0.042);
  root.add(displayMesh);

  // Anchor
  const anchor = new THREE.Object3D();
  anchor.name = 'sensor_anchor';
  anchor.position.set(0, 0, 0);
  root.add(anchor);

  return exportToGLB(root);
}

const BUILDERS = {
  'compressor.glb': {
    build: buildCompressor,
    type: 'COMPRESSOR',
    anchors: { port_OUT: [0.8, 0.5, 0.0] },
    node_names: ['port_OUT', 'rotor', 'gauge'],
  },
  'tank.glb': {
    build: buildTank,
    type: 'TANK',
    anchors: { port_A: [-0.45, 0.9, 0.0], port_B: [0.45, 0.9, 0.0] },
    node_names: ['port_A', 'port_B', 'gauge'],
  },
  'isolation-valve.glb': {
    build: buildIsolationValve,
    type: 'ISOLATION_VALVE',
    anchors: { port_A: [-0.2, 0.3, 0.0], port_B: [0.2, 0.3, 0.0] },
    node_names: ['port_A', 'port_B', 'handle'],
  },
  'control-valve.glb': {
    build: buildControlValve,
    type: 'CONTROL_VALVE',
    anchors: { port_A: [-0.2, 0.3, 0.0], port_B: [0.2, 0.3, 0.0] },
    node_names: ['port_A', 'port_B', 'indicator'],
  },
  'demand.glb': {
    build: buildDemand,
    type: 'DEMAND',
    anchors: { port_IN: [-0.4, 0.6, 0.0] },
    node_names: ['port_IN'],
  },
  'pressure-sensor.glb': {
    build: buildPressureSensor,
    type: 'PRESSURE_SENSOR',
    anchors: { sensor_anchor: [0.0, 0.0, 0.0] },
    node_names: ['sensor_anchor', 'needle'],
  },
  'flow-sensor.glb': {
    build: buildFlowSensor,
    type: 'FLOW_SENSOR',
    anchors: { sensor_anchor: [0.0, 0.0, 0.0] },
    node_names: ['sensor_anchor'],
  },
};

async function main() {
  const isCheckMode = process.argv.includes('--check');
  fs.mkdirSync(PUBLIC_DIR, { recursive: true });

  const manifestPath = path.join(PUBLIC_DIR, 'catalog.json');
  const manifest = {
    schema_version: 'lab-asset-manifest-v1',
    origin: 'PROJECT_AUTHORED',
    license: 'MIT',
    units: 'meter',
    lod_distances_m: [12.0, 24.0],
    assets: {},
  };

  let allMatches = true;

  for (const [filename, info] of Object.entries(BUILDERS)) {
    const glbBuffer = await info.build();
    const sha256 = crypto.createHash('sha256').update(glbBuffer).digest('hex');
    const targetFile = path.join(PUBLIC_DIR, filename);

    manifest.assets[filename] = {
      filename,
      type: info.type,
      sha256,
      size_bytes: glbBuffer.length,
      anchors: info.anchors,
      node_names: info.node_names,
      lod_distances_m: [12.0, 24.0],
    };

    if (isCheckMode) {
      if (!fs.existsSync(targetFile)) {
        console.error(`Check failed: ${filename} missing on disk.`);
        allMatches = false;
        continue;
      }
      const existingBuffer = fs.readFileSync(targetFile);
      const existingSha = crypto.createHash('sha256').update(existingBuffer).digest('hex');
      if (existingSha !== sha256) {
        console.error(`Check failed: ${filename} SHA mismatch. Disk: ${existingSha}, Generated: ${sha256}`);
        allMatches = false;
      }
    } else {
      fs.writeFileSync(targetFile, glbBuffer);
      console.log(`Wrote ${filename} (${glbBuffer.length} bytes, SHA: ${sha256.slice(0, 12)}...)`);
    }
  }

  const manifestJson = JSON.stringify(manifest, null, 2) + '\n';
  if (isCheckMode) {
    if (!fs.existsSync(manifestPath)) {
      console.error('Check failed: catalog.json missing.');
      allMatches = false;
    } else {
      const existingManifest = fs.readFileSync(manifestPath, 'utf-8');
      if (existingManifest !== manifestJson) {
        console.error('Check failed: catalog.json content mismatch.');
        allMatches = false;
      }
    }
    if (!allMatches) {
      process.exit(1);
    }
    console.log('All 3D assets and manifest match checked state.');
    process.exit(0);
  } else {
    fs.writeFileSync(manifestPath, manifestJson, 'utf-8');
    console.log(`Wrote catalog manifest to ${manifestPath}`);
  }
}

main().catch((err) => {
  console.error('Failed to generate lab assets:', err);
  process.exit(1);
});

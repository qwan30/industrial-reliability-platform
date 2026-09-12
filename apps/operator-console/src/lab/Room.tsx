/**
 * 24x16m Industrial Training Room with floor grid, columns, trusses, and lighting.
 */


export function Room() {
  const roomWidth = 24.0;
  const roomDepth = 16.0;
  const wallHeight = 5.0;

  // Grid texture or line markers
  return (
    <group name="FACTORY_ROOM">
      {/* Lighting */}
      <ambientLight intensity={0.45} />
      <directionalLight
        position={[10, 16, 8]}
        intensity={1.1}
        castShadow
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-near={0.5}
        shadow-camera-far={40}
        shadow-camera-left={-15}
        shadow-camera-right={15}
        shadow-camera-top={10}
        shadow-camera-bottom={-10}
      />
      <hemisphereLight args={[0xddeeff, 0x334455, 0.4]} />

      {/* Ceiling panel light accents */}
      {[-8, 0, 8].map((x) =>
        [-4, 4].map((z) => (
          <group key={`light_${x}_${z}`} position={[x, wallHeight - 0.1, z]}>
            <mesh>
              <boxGeometry args={[2.0, 0.08, 0.8]} />
              <meshStandardMaterial color={0xffffff} emissive={0xf0f4f8} emissiveIntensity={0.8} />
            </mesh>
            <pointLight distance={10} intensity={0.3} decay={2} />
          </group>
        ))
      )}

      {/* Concrete Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
        <planeGeometry args={[roomWidth, roomDepth]} />
        <meshStandardMaterial color={0xb8bec4} roughness={0.95} metalness={0.05} />
      </mesh>

      {/* Subtle floor grid */}
      <gridHelper args={[24, 24, 0x6b7785, 0x8f9ba8]} position={[0, 0, 0]} />

      {/* Safety lane stripes (outer border at [-11, 11] x [-7, 7]) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, -7.2]}>
        <planeGeometry args={[roomWidth - 1, 0.2]} />
        <meshStandardMaterial color={0xd4a017} roughness={0.5} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, 7.2]}>
        <planeGeometry args={[roomWidth - 1, 0.2]} />
        <meshStandardMaterial color={0xd4a017} roughness={0.5} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[-11.2, 0.002, 0]}>
        <planeGeometry args={[0.2, roomDepth - 1]} />
        <meshStandardMaterial color={0xd4a017} roughness={0.5} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[11.2, 0.002, 0]}>
        <planeGeometry args={[0.2, roomDepth - 1]} />
        <meshStandardMaterial color={0xd4a017} roughness={0.5} />
      </mesh>

      {/* Perimeter steel structural columns */}
      {[-11.5, 11.5].map((x) =>
        [-7.5, 0, 7.5].map((z) => (
          <mesh key={`col_${x}_${z}`} position={[x, wallHeight / 2, z]} castShadow receiveShadow>
            <boxGeometry args={[0.3, wallHeight, 0.3]} />
            <meshStandardMaterial color={0x525e6b} roughness={0.6} metalness={0.6} />
          </mesh>
        ))
      )}

      {/* Roof trusses */}
      {[-7.5, 0, 7.5].map((z) => (
        <mesh key={`truss_${z}`} position={[0, wallHeight - 0.15, z]}>
          <boxGeometry args={[roomWidth - 0.6, 0.2, 0.2]} />
          <meshStandardMaterial color={0x414c57} roughness={0.5} metalness={0.7} />
        </mesh>
      ))}
    </group>
  );
}

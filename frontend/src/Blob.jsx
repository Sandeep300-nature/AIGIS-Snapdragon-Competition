import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import './Blob.css';

export default function Blob({ 
  blobParams, 
  onUpdateParam, 
  currentState = 'idle', // 'idle' | 'listening' | 'thinking' | 'speaking' | 'error'
  currentMood = 'cyan',   // 'cyan' | 'red' | 'green' | 'violet' | 'amber'
  micError = null 
}) {
  const containerRef = useRef(null);
  const paramsRef = useRef(blobParams);
  const stateRef = useRef(currentState);
  const moodRef = useRef(currentMood);

  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const dataArrayRef = useRef(null);
  const micStreamRef = useRef(null);
  const audioVolumeRef = useRef(0);
  const smoothDistortionRef = useRef(0);
  const currentScaleRef = useRef(1.0);

  // Define mood color schemes
  const moodColors = {
    cyan: { mid: 0x00bfff, bright: 0x00ffe1, hexMid: '#00bfff', hexBright: '#00ffe1' },
    red: { mid: 0xff3366, bright: 0xff4d4d, hexMid: '#ff3366', hexBright: '#ff4d4d' },
    green: { mid: 0x00cc77, bright: 0x00ffaa, hexMid: '#00cc77', hexBright: '#00ffaa' },
    violet: { mid: 0x8a2be2, bright: 0xc084fc, hexMid: '#8a2be2', hexBright: '#c084fc' },
    amber: { mid: 0xffaa00, bright: 0xffd700, hexMid: '#ffaa00', hexBright: '#ffd700' },
  };

  // Keep refs in sync with incoming props
  useEffect(() => {
    paramsRef.current = blobParams;
  }, [blobParams]);

  useEffect(() => {
    stateRef.current = currentState;
  }, [currentState]);

  useEffect(() => {
    moodRef.current = currentMood;
  }, [currentMood]);

  // Sync Microphone activation with blobParams.isMicActive
  useEffect(() => {
    if (blobParams.isMicActive) {
      startMicrophone();
    } else {
      stopMicrophone();
    }
  }, [blobParams.isMicActive]);

  const startMicrophone = async () => {
    if (micStreamRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      micStreamRef.current = stream;

      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioContextClass();
      if (audioCtx.state === 'suspended') {
        await audioCtx.resume();
      }
      audioContextRef.current = audioCtx;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.85;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      dataArrayRef.current = new Uint8Array(analyser.frequencyBinCount);
    } catch (err) {
      console.warn('Microphone visualization notice:', err);
    }
  };

  const stopMicrophone = () => {
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((track) => track.stop());
      micStreamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    audioVolumeRef.current = 0;
  };

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const width = container.clientWidth || 340;
    const height = container.clientHeight || 340;

    // 1. SCENE SETUP
    const scene = new THREE.Scene();
    scene.background = null;

    const camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 100);
    camera.position.z = 2.4;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.95;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.minDistance = 2.4;
    controls.maxDistance = 2.4;

    // GROUP FOR ROTATION & SHAPE
    const mainGroup = new THREE.Group();
    scene.add(mainGroup);

    // GLSL NOISE FUNCTIONS
    const noiseFunctions = `
        vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
        vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
        vec4 permute(vec4 x) { return mod289(((x*34.0)+1.0)*x); }
        vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

        float snoise(vec3 v) {
            const vec2 C = vec2(1.0/6.0, 1.0/3.0);
            const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
            vec3 i  = floor(v + dot(v, C.yyy) );
            vec3 x0 = v - i + dot(i, C.xxx) ;
            vec3 g = step(x0.yzx, x0.xyz);
            vec3 l = 1.0 - g;
            vec3 i1 = min( g.xyz, l.zxy );
            vec3 i2 = max( g.xyz, l.zxy );
            vec3 x1 = x0 - i1 + C.xxx;
            vec3 x2 = x0 - i2 + C.yyy;
            vec3 x3 = x0 - D.yyy;
            i = mod289(i);
            vec4 p = permute( permute( permute(
                        i.z + vec4(0.0, i1.z, i2.z, 1.0 ))
                    + i.y + vec4(0.0, i1.y, i2.y, 1.0 ))
                    + i.x + vec4(0.0, i1.x, i2.x, 1.0 ));
            float n_ = 0.142857142857;
            vec3  ns = n_ * D.wyz - D.xzx;
            vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
            vec4 x_ = floor(j * ns.z);
            vec4 y_ = floor(j - 7.0 * x_ );
            vec4 x = x_ *ns.x + ns.yyyy;
            vec4 y = y_ *ns.x + ns.yyyy;
            vec4 h = 1.0 - abs(x) - abs(y);
            vec4 b0 = vec4( x.xy, y.xy );
            vec4 b1 = vec4( x.zw, y.zw );
            vec4 s0 = floor(b0)*2.0 + 1.0;
            vec4 s1 = floor(b1)*2.0 + 1.0;
            vec4 sh = -step(h, vec4(0.0));
            vec4 a0 = b0.xzyw + s0.xzyw*sh.xxyy ;
            vec4 a1 = b1.xzyw + s1.xzyw*sh.zzww ;
            vec3 p0 = vec3(a0.xy,h.x);
            vec3 p1 = vec3(a0.zw,h.y);
            vec3 p2 = vec3(a1.xy,h.z);
            vec3 p3 = vec3(a1.zw,h.w);
            vec4 norm = taylorInvSqrt(vec4(dot(p0,p0), dot(p1,p1), dot(p2, p2), dot(p3,p3)));
            p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
            vec4 m = max(0.6 - vec4(dot(x0,x0), dot(x1,x1), dot(x2,x2), dot(x3,x3)), 0.0);
            m = m * m;
            return 42.0 * dot( m*m, vec4( dot(p0,x0), dot(p1,x1), dot(p2,x2), dot(p3,x3) ) );
        }

        float fbm(vec3 p) {
            float total = 0.0;
            float amplitude = 0.5;
            float frequency = 1.0;
            for (int i = 0; i < 3; i++) { 
                total += snoise(p * frequency) * amplitude;
                amplitude *= 0.5;
                frequency *= 2.0;
            }
            return total;
        }
    `;

    // 2. LIGHTS
    const pointLight = new THREE.PointLight(0x00bfff, 2.2, 10);
    mainGroup.add(pointLight);

    // 3. OUTER SHELL
    const shellGeo = new THREE.SphereGeometry(0.85, 128, 128);

    const shellVertexShader = `
        uniform float uTime;
        uniform float uDisplacement;

        varying vec3 vNormal;
        varying vec3 vViewPosition;

        ${noiseFunctions}

        void main() {
            vec3 pos = position;
            
            if (uDisplacement > 0.0001) {
                float macroNoise = snoise(normal * 1.3 + vec3(uTime * 0.4, uTime * 0.3, uTime * 0.5));
                float microNoise = snoise(normal * 2.8 - vec3(uTime * 0.6, uTime * 0.5, uTime * 0.7)) * 0.45;
                float blobShape = (macroNoise + microNoise);
                pos += normal * (blobShape * uDisplacement);
            }

            vNormal = normalize(normalMatrix * normal);
            vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
            vViewPosition = -mvPosition.xyz;
            gl_Position = projectionMatrix * mvPosition;
        }
    `;

    const shellFragmentShader = `
        varying vec3 vNormal;
        varying vec3 vViewPosition;
        uniform vec3 uColor;
        uniform float uOpacity;
        
        void main() {
            float fresnel = pow(1.0 - dot(normalize(vNormal), normalize(vViewPosition)), 2.5);
            gl_FragColor = vec4(uColor, fresnel * uOpacity);
        }
    `;

    const shellBackMat = new THREE.ShaderMaterial({
      vertexShader: shellVertexShader,
      fragmentShader: shellFragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uDisplacement: { value: 0.0 },
        uColor: { value: new THREE.Color(0x000833) },
        uOpacity: { value: 0.35 },
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false,
    });

    const shellFrontMat = new THREE.ShaderMaterial({
      vertexShader: shellVertexShader,
      fragmentShader: shellFragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uDisplacement: { value: 0.0 },
        uColor: { value: new THREE.Color(0x00e1ff) },
        uOpacity: { value: 0.45 },
      },
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.FrontSide,
      depthWrite: false,
    });

    mainGroup.add(new THREE.Mesh(shellGeo, shellBackMat));
    mainGroup.add(new THREE.Mesh(shellGeo, shellFrontMat));

    // 4. PLASMA CORE
    const plasmaGeo = new THREE.SphereGeometry(0.848, 128, 128);
    const plasmaMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uDisplacement: { value: 0.0 },
        uScale: { value: paramsRef.current.plasmaScale || 0.22 },
        uBrightness: { value: paramsRef.current.plasmaBrightness || 1.4 },
        uThreshold: { value: 0.09 },
        uColorDeep: { value: new THREE.Color(0x000c1e) },
        uColorMid: { value: new THREE.Color(paramsRef.current.colorMid || '#00bfff') },
        uColorBright: { value: new THREE.Color(paramsRef.current.colorBright || '#00ffe1') },
      },
      vertexShader: `
            uniform float uTime;
            uniform float uDisplacement;

            varying vec3 vPosition;
            varying vec3 vNormal;
            varying vec3 vViewPosition;

            ${noiseFunctions}

            void main() {
                vec3 pos = position;
                
                if (uDisplacement > 0.0001) {
                    float macroNoise = snoise(normal * 1.3 + vec3(uTime * 0.4, uTime * 0.3, uTime * 0.5));
                    float microNoise = snoise(normal * 2.8 - vec3(uTime * 0.6, uTime * 0.5, uTime * 0.7)) * 0.45;
                    float blobShape = (macroNoise + microNoise);
                    pos += normal * (blobShape * uDisplacement);
                }

                vPosition = pos;
                vNormal = normalize(normalMatrix * normal);
                vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
                vViewPosition = -mvPosition.xyz; 
                gl_Position = projectionMatrix * mvPosition;
            }
        `,
      fragmentShader: `
            uniform float uTime;
            uniform float uScale;
            uniform float uBrightness;
            uniform float uThreshold;
            uniform vec3 uColorDeep;
            uniform vec3 uColorMid;
            uniform vec3 uColorBright;

            varying vec3 vPosition;
            varying vec3 vNormal;
            varying vec3 vViewPosition;
            
            ${noiseFunctions}

            void main() {
                vec3 p = vPosition * uScale; 
                
                vec3 q = vec3(
                    fbm(p + vec3(0.0, uTime * 0.05, 0.0)),
                    fbm(p + vec3(5.2, 1.3, 2.8) + uTime * 0.05),
                    fbm(p + vec3(2.2, 8.4, 0.5) - uTime * 0.02)
                );
                
                float density = fbm(p + 2.0 * q);
                float t = (density + 0.4) * 0.8;
                float alpha = smoothstep(uThreshold, 0.7, t);

                vec3 cWhite = vec3(1.0, 1.0, 1.0);
                
                vec3 color = mix(uColorDeep, uColorMid, smoothstep(uThreshold, 0.5, t));
                color = mix(color, uColorBright, smoothstep(0.5, 0.8, t));
                color = mix(color, cWhite, smoothstep(0.8, 1.0, t));

                float facing = dot(normalize(vNormal), normalize(vViewPosition));
                float depthFactor = (facing + 1.0) * 0.5;
                float finalAlpha = alpha * (0.02 + 0.98 * depthFactor);
                
                gl_FragColor = vec4(color * uBrightness, finalAlpha);
            }
        `,
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.DoubleSide,
      depthWrite: false,
    });

    const plasmaMesh = new THREE.Mesh(plasmaGeo, plasmaMat);
    mainGroup.add(plasmaMesh);

    // 5. PARTICLES
    const pCount = 500;
    const pPos = new Float32Array(pCount * 3);
    const pSizes = new Float32Array(pCount);
    const sphereRadius = 0.82;

    for (let i = 0; i < pCount; i++) {
      const r = sphereRadius * Math.cbrt(Math.random());
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      pPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pPos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pPos[i * 3 + 2] = r * Math.cos(phi);

      pSizes[i] = Math.random();
    }

    const pGeo = new THREE.BufferGeometry();
    pGeo.setAttribute('position', new THREE.BufferAttribute(pPos, 3));
    pGeo.setAttribute('aSize', new THREE.BufferAttribute(pSizes, 1));

    const pMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new THREE.Color(0xffffff) },
      },
      vertexShader: `
            uniform float uTime;
            attribute float aSize;
            varying float vAlpha;
            
            void main() {
                vec3 pos = position;
                pos.y += sin(uTime * 0.2 + pos.x) * 0.02;
                pos.x += cos(uTime * 0.15 + pos.z) * 0.02;

                vec4 mvPosition = modelViewMatrix * vec4(pos, 1.0);
                gl_Position = projectionMatrix * mvPosition;
                
                float baseSize = 7.0 * aSize + 3.0;
                gl_PointSize = baseSize * (1.0 / -mvPosition.z);
                
                vAlpha = 0.8 + 0.2 * sin(uTime + aSize * 10.0);
            }
        `,
      fragmentShader: `
            uniform vec3 uColor;
            varying float vAlpha;
            void main() {
                vec2 uv = gl_PointCoord - vec2(0.5);
                float dist = length(uv);
                if(dist > 0.5) discard;
                
                float glow = 1.0 - (dist * 2.0);
                glow = pow(glow, 1.8);
                
                gl_FragColor = vec4(uColor, glow * vAlpha);
            }
        `,
      transparent: true,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });

    const particles = new THREE.Points(pGeo, pMat);
    mainGroup.add(particles);

    // 6. ANIMATION LOOP WITH STATE & MOOD LERPING
    const clock = new THREE.Clock();
    let animationFrameId;

    const targetColorMid = new THREE.Color();
    const targetColorBright = new THREE.Color();

    function animate() {
      animationFrameId = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();

      const currentParams = paramsRef.current;
      const st = stateRef.current;
      const moodKey = st === 'error' ? 'red' : moodRef.current;

      // Determine colors according to mood/error state
      const targetMood = moodColors[moodKey] || moodColors.cyan;
      targetColorMid.setHex(targetMood.mid);
      targetColorBright.setHex(targetMood.bright);

      // Smooth color lerp
      plasmaMat.uniforms.uColorMid.value.lerp(targetColorMid, 0.05);
      plasmaMat.uniforms.uColorBright.value.lerp(targetColorBright, 0.05);
      shellFrontMat.uniforms.uColor.value.lerp(targetColorBright, 0.05);
      pointLight.color.lerp(targetColorMid, 0.05);

      // ----------------------------------------------------
      // STATE-BASED SCALE & ANIMATION DYNAMICS (User Request)
      // ----------------------------------------------------
      let targetScale = 1.0;
      let targetRotSpeedY = currentParams.rotationSpeedY;
      let targetRotSpeedX = 0;
      let pulseFactor = 0;
      let brightnessTarget = currentParams.plasmaBrightness || 1.4;

      if (st === 'listening') {
        // 🎙️ Expand slightly while listening
        targetScale = 1.12;
        brightnessTarget = 1.6;
      } else if (st === 'thinking') {
        // 🧐 Slowly/faster rotate while thinking + high energy plasma
        targetScale = 1.05;
        targetRotSpeedY = 0.025; // Faster rotation
        targetRotSpeedX = 0.015; // Multi-axis spin
        brightnessTarget = 1.8;
      } else if (st === 'speaking') {
        // 💙 Pulse while speaking
        pulseFactor = Math.sin(t * 10) * 0.06;
        targetScale = 1.06 + pulseFactor;
        brightnessTarget = 1.9 + Math.sin(t * 8) * 0.3;
      } else if (st === 'idle') {
        // 😴 Dim when idle
        targetScale = 0.96;
        brightnessTarget = 1.1; // Dimmed when idle
      } else if (st === 'error') {
        // ❤️ Error state pulsing red
        pulseFactor = Math.sin(t * 6) * 0.04;
        targetScale = 1.04 + pulseFactor;
        brightnessTarget = 1.7;
      }

      // Smooth scale interpolation
      currentScaleRef.current += (targetScale - currentScaleRef.current) * 0.08;
      mainGroup.scale.set(currentScaleRef.current, currentScaleRef.current, currentScaleRef.current);

      // Audio volume calculation from Mic
      let rawVolume = 0;
      if (analyserRef.current && dataArrayRef.current && blobParams.isMicActive) {
        analyserRef.current.getByteFrequencyData(dataArrayRef.current);
        let sum = 0;
        for (let i = 0; i < dataArrayRef.current.length; i++) {
          sum += dataArrayRef.current[i];
        }
        rawVolume = sum / dataArrayRef.current.length / 255;
      }

      if (rawVolume < 0.02) rawVolume = 0;

      audioVolumeRef.current += (rawVolume - audioVolumeRef.current) * 0.1;
      const currentVol = audioVolumeRef.current * currentParams.micSensitivity;

      const targetDistortion = (currentVol * (currentParams.jiggleAmount || 0.35) * 0.75) + (st === 'thinking' ? 0.08 : 0);
      smoothDistortionRef.current += (targetDistortion - smoothDistortionRef.current) * 0.1;

      let waveDisplacement = smoothDistortionRef.current;
      if (waveDisplacement < 0.0005) waveDisplacement = 0.0;

      const effectiveTimeScale = st === 'thinking' ? currentParams.timeScale * 2.2 : currentParams.timeScale;
      const currentTime = t * 0.4 * effectiveTimeScale;

      plasmaMat.uniforms.uTime.value = currentTime;
      plasmaMat.uniforms.uDisplacement.value = waveDisplacement;
      shellFrontMat.uniforms.uTime.value = currentTime;
      shellFrontMat.uniforms.uDisplacement.value = waveDisplacement;
      shellBackMat.uniforms.uTime.value = currentTime;
      shellBackMat.uniforms.uDisplacement.value = waveDisplacement;

      plasmaMat.uniforms.uScale.value = (currentParams.plasmaScale || 0.22) + currentVol * 0.04;
      plasmaMat.uniforms.uBrightness.value = brightnessTarget + currentVol * 0.8;

      pMat.uniforms.uTime.value = t;

      plasmaMesh.rotation.y = t * 0.04;
      mainGroup.rotation.y += targetRotSpeedY;
      if (targetRotSpeedX > 0) {
        mainGroup.rotation.x += targetRotSpeedX;
      } else {
        mainGroup.rotation.x += (0 - mainGroup.rotation.x) * 0.05; // Reset X tilt smoothly
      }

      controls.update();
      renderer.render(scene, camera);
    }

    const handleResize = () => {
      const newWidth = container.clientWidth || 340;
      const newHeight = container.clientHeight || 340;
      camera.aspect = newWidth / newHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(newWidth, newHeight);
    };

    window.addEventListener('resize', handleResize);
    animate();

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener('resize', handleResize);
      controls.dispose();
      renderer.dispose();

      shellGeo.dispose();
      shellBackMat.dispose();
      shellFrontMat.dispose();
      plasmaGeo.dispose();
      plasmaMat.dispose();
      pGeo.dispose();
      pMat.dispose();

      if (container && renderer.domElement) {
        container.removeChild(renderer.domElement);
      }
      stopMicrophone();
    };
  }, []);

  // Map state to badge symbol and title (Matching user mock image 1)
  const getStateInfo = () => {
    switch (currentState) {
      case 'listening':
        return { label: 'Listening', symbol: '))•((', class: 'listening' };
      case 'thinking':
        return { label: 'Thinking', symbol: '◐', class: 'thinking' };
      case 'speaking':
        return { label: 'Speaking', symbol: '✨•✨', class: 'speaking' };
      case 'error':
        return { label: 'Error / Offline', symbol: '⚠️', class: 'error' };
      case 'idle':
      default:
        return { label: 'Idle', symbol: '•', class: 'idle' };
    }
  };

  const stateInfo = getStateInfo();

  return (
    <div className="blob-wrapper">
      {/* State Badge Overlay (Image 1 match) */}
      <div className={`orb-state-badge glass-panel ${stateInfo.class}`}>
        <span className="state-label">{stateInfo.label}</span>
        <span className="state-symbol">{stateInfo.symbol}</span>
      </div>

      <div ref={containerRef} className="blob-canvas-container" />

      <div className="blob-ui-overlay">
        {blobParams.isMicActive && (
          <div className="audio-indicator">
            <span className="pulse-dot"></span>
            <span>Listening to voice...</span>
          </div>
        )}

        {micError && <div className="mic-error-badge">{micError}</div>}
      </div>
    </div>
  );
}

'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { KS } from '@/components/keystone/keystone-content';

/**
 * "Fig. 01 — Schema solid": nine stacked hexagonal courses with inked edges,
 * two survey dials, three sighting markers, and a bronze core floating above
 * the stack. The solid answers to the pointer (a critically-damped spring on
 * two axes) and to page scroll, which both rotates the stack and dollies the
 * camera down onto it.
 *
 * Ported from the Keystone landing. Mounted only through
 * {@link TriangulationSolid}, which gates it on device capability and loads it
 * with `ssr: false` so `three` never enters a chat route's bundle.
 */
export function TriangulationScene({
  accent = KS.bronze,
  spinSpeed = 0.06,
  onUnavailable,
}: {
  accent?: string;
  spinSpeed?: number;
  /** Called when WebGL cannot be initialised, so the caller draws the plate. */
  onUnavailable?: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const accentColor = new THREE.Color(accent);
    const stone = new THREE.Color(KS.stone);

    // A context is not guaranteed: blocklisted drivers, exhausted context
    // slots, and headless browsers all throw here. Falling back is the only
    // correct response — letting this propagate takes the page down with it.
    // Three owns its canvas rather than binding to one in the JSX: a context
    // that has been force-lost cannot be re-acquired on the same element,
    // which would break StrictMode's second mount.
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      onUnavailable?.();
      return;
    }
    renderer.domElement.style.cssText =
      'position:absolute;inset:0;width:100%;height:100%;display:block';
    host.appendChild(renderer.domElement);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    // PCFSoftShadowMap was removed in three r186 (this repo pins ^0.186);
    // it silently fell back to PCFShadowMap and logged a deprecation on
    // every mount. Asking for what actually exists is the same picture.
    renderer.shadowMap.type = THREE.PCFShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;

    const scene = new THREE.Scene();
    const FOV = 34;
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
    camera.position.set(0, 2.6, 9.2);
    camera.lookAt(0, 0.5, 0);

    const key = new THREE.DirectionalLight(0xfff4e2, 3.1);
    key.position.set(-4.5, 7.5, 4.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.radius = 5;
    key.shadow.camera.near = 1;
    key.shadow.camera.far = 24;
    key.shadow.camera.left = -6;
    key.shadow.camera.right = 6;
    key.shadow.camera.top = 6;
    key.shadow.camera.bottom = -6;
    scene.add(key);

    const rim = new THREE.DirectionalLight(0xcfd8e6, 1.5);
    rim.position.set(5, 1.6, -5.5);
    scene.add(rim);
    scene.add(new THREE.HemisphereLight(0xf6f1e6, 0x8d8371, 0.55));

    // Shadow-only ground: catches the stack's cast shadow without painting a
    // plane over the paper background.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(40, 40),
      new THREE.ShadowMaterial({ opacity: 0.19 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -1.62;
    ground.receiveShadow = true;
    scene.add(ground);

    const disposables: Array<{ dispose(): void }> = [ground.geometry, ground.material];
    const solid = new THREE.Group();
    solid.position.y = -0.1;
    scene.add(solid);

    const LAYERS = 9;
    for (let i = 0; i < LAYERS; i += 1) {
      const t = i / (LAYERS - 1);
      const radius = 2.35 - t * 1.75;
      const geometry = new THREE.CylinderGeometry(radius * 0.93, radius, 0.16, 6, 1);
      const material = new THREE.MeshStandardMaterial({
        color: stone,
        roughness: 0.85 - t * 0.15,
        metalness: 0.04,
      });
      const course = new THREE.Mesh(geometry, material);
      course.position.y = -1.45 + i * 0.315;
      course.rotation.y = i * 0.146;
      course.castShadow = true;
      course.receiveShadow = true;
      solid.add(course);
      disposables.push(geometry, material);

      const edgeGeometry = new THREE.TorusGeometry(radius * 0.995, 0.006, 6, 6);
      const edgeMaterial = new THREE.MeshStandardMaterial({
        color: 0x2a2c2e,
        roughness: 0.6,
        metalness: 0.2,
      });
      const edge = new THREE.Mesh(edgeGeometry, edgeMaterial);
      edge.rotation.x = Math.PI / 2;
      edge.rotation.z = i * 0.146;
      edge.position.y = course.position.y + 0.081;
      solid.add(edge);
      disposables.push(edgeGeometry, edgeMaterial);
    }

    const coreGeometry = new THREE.IcosahedronGeometry(0.5, 0);
    // Kept well below full metalness: with only analytic lights and no
    // environment map, a near-1 metalness core renders almost black and loses
    // the bronze entirely.
    const coreMaterial = new THREE.MeshStandardMaterial({
      color: accentColor,
      roughness: 0.28,
      metalness: 0.35,
    });
    const core = new THREE.Mesh(coreGeometry, coreMaterial);
    core.position.y = 1.62;
    core.castShadow = true;
    solid.add(core);
    disposables.push(coreGeometry, coreMaterial);

    const dialGeometry = new THREE.TorusGeometry(2.85, 0.018, 8, 128);
    const dialMaterial = new THREE.MeshStandardMaterial({
      color: 0x3a3c3e,
      roughness: 0.35,
      metalness: 0.9,
    });
    const dial = new THREE.Mesh(dialGeometry, dialMaterial);
    dial.rotation.x = Math.PI / 2 - 0.34;
    dial.position.y = 0.1;
    solid.add(dial);
    const dialCross = new THREE.Mesh(dialGeometry, dialMaterial);
    dialCross.rotation.x = Math.PI / 2 + 0.34;
    dialCross.rotation.z = 0.6;
    dialCross.position.y = 0.1;
    solid.add(dialCross);
    disposables.push(dialGeometry, dialMaterial);

    // Three sighting markers on the dial.
    const markerGeometry = new THREE.BoxGeometry(0.055, 0.055, 0.6);
    const markerMaterial = new THREE.MeshStandardMaterial({
      color: accentColor,
      roughness: 0.3,
      metalness: 0.3,
    });
    for (let i = 0; i < 3; i += 1) {
      const angle = (i / 3) * Math.PI * 2 + 0.4;
      const marker = new THREE.Mesh(markerGeometry, markerMaterial);
      marker.position.set(Math.cos(angle) * 2.85, 0.1, Math.sin(angle) * 2.85);
      marker.lookAt(0, 0.1, 0);
      solid.add(marker);
    }
    disposables.push(markerGeometry, markerMaterial);

    const pointer = { x: 0, y: 0 };
    const onPointerMove = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      pointer.y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    // Frame the solid's bounding radius at any aspect so it never crops.
    const SOLID_RADIUS = 3.25;
    let baseZ = 9.2;
    const fit = (width: number, height: number) => {
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      const aspect = width / height;
      camera.aspect = aspect;
      const halfFov = Math.tan((FOV * Math.PI) / 360);
      baseZ = Math.max(9.2, SOLID_RADIUS / (halfFov * Math.min(1, aspect)));
      camera.updateProjectionMatrix();
    };
    fit(host.clientWidth, host.clientHeight);

    const resizeObserver = new ResizeObserver(([entry]) => {
      fit(entry.contentRect.width, entry.contentRect.height);
    });
    resizeObserver.observe(host);

    const rotation = { x: 0, y: 0, vx: 0, vy: 0 };
    let frame = 0;
    let onScreen = true;
    let last = performance.now();

    // Scroll past the hero or background the tab and the loop stops entirely
    // rather than burning frames on an off-screen canvas.
    const running = () => onScreen && document.visibilityState === 'visible';

    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;

      const scrollable = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
      const progress = Math.min(window.scrollY / scrollable, 1);

      // Critically-damped spring toward the pointer- and scroll-derived target.
      const targetY = pointer.x * 0.42 + progress * 3.4;
      const targetX = -pointer.y * 0.26 + progress * 0.45;
      const stiffness = 68;
      const damping = 12;
      rotation.vy += (targetY - rotation.y) * stiffness * dt - rotation.vy * damping * dt;
      rotation.vx += (targetX - rotation.x) * stiffness * dt - rotation.vx * damping * dt;
      rotation.y += rotation.vy * dt;
      rotation.x += rotation.vx * dt;

      solid.rotation.y = rotation.y + now * 0.001 * spinSpeed;
      solid.rotation.x = rotation.x;
      core.rotation.y = now * 0.0004;
      core.rotation.x = now * 0.00026;
      core.position.y = 1.62 + Math.sin(now * 0.0011) * 0.075;

      camera.position.y = 2.6 - progress * 1.5;
      camera.position.z = baseZ - progress * 1.1;
      camera.lookAt(0, 0.5 - progress * 0.3, 0);

      renderer.render(scene, camera);
      frame = running() ? requestAnimationFrame(tick) : 0;
    };

    const sync = () => {
      if (running() && frame === 0) {
        last = performance.now();
        frame = requestAnimationFrame(tick);
      } else if (!running() && frame !== 0) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    };

    const visibilityObserver = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        sync();
      },
      { threshold: 0.02 },
    );
    visibilityObserver.observe(host);
    document.addEventListener('visibilitychange', sync);

    // Paint once up front. A page opened in a background tab (or restored from
    // one) starts paused, and without this the canvas sits empty until it
    // resumes.
    renderer.render(scene, camera);
    sync();

    return () => {
      if (frame) cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onPointerMove);
      document.removeEventListener('visibilitychange', sync);
      visibilityObserver.disconnect();
      resizeObserver.disconnect();
      disposables.forEach((item) => item.dispose());
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [accent, onUnavailable, spinSpeed]);

  return <div ref={hostRef} aria-hidden className="absolute inset-0" />;
}

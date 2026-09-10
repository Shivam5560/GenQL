'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';

/**
 * "Schema resolving into an answer": a loose cluster of thin table-shaped
 * panels (wireframe rectangles, like ER-diagram nodes lifted into 3D)
 * connected by thin foreign-key-style edges. One edge carries the brand
 * accent — every other line reads at the app's muted, low-contrast tone.
 *
 * Built with raw `three` (no react-three-fiber) inside a `useEffect`,
 * mirroring the reference pattern from Professional_Grade_RAG's
 * `TriangulationScene`: the renderer owns its own canvas (a lost WebGL
 * context cannot be re-acquired on the same element, which matters for
 * StrictMode's double-invoke), every geometry/material is tracked in a
 * `disposables` array and torn down on unmount, and context creation is
 * wrapped in try/catch so a blocklisted driver or exhausted context budget
 * falls back instead of taking the page down.
 *
 * Mounted only through {@link SchemaSceneBackdrop}, which gates it on
 * reduced-motion and loads it with `ssr: false`.
 */
export function SchemaScene({
  onUnavailable,
}: {
  /** Called when WebGL cannot be initialised, so the caller can fall back. */
  onUnavailable?: () => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const style = getComputedStyle(document.documentElement);
    const lineColor = parseCssColor(style.getPropertyValue('--line'), '#0a0a0a');
    const muteColor = parseCssColor(style.getPropertyValue('--mute'), '#5c594e');
    const brandColor = parseCssColor(style.getPropertyValue('--brand'), '#ff5a1f');

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
    renderer.setClearColor(0x000000, 0);

    const scene = new THREE.Scene();
    const FOV = 42;
    const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 100);
    camera.position.set(0, 0, 7.2);

    const disposables: Array<{ dispose(): void }> = [];
    const cluster = new THREE.Group();
    scene.add(cluster);

    // Fixed, hand-placed panel layout rather than Math.random(): a table-schema
    // cluster should read as deliberate, not scattered. Loosely spherical so no
    // rotation axis reveals a flat arrangement.
    const PANELS: Array<{
      position: [number, number, number];
      rotation: [number, number, number];
      size: [number, number];
    }> = [
      { position: [-1.7, 0.9, 0.4], rotation: [0.3, 0.5, 0.1], size: [1.15, 0.75] },
      { position: [0.3, 1.5, -0.6], rotation: [-0.2, 0.9, 0.2], size: [0.95, 0.6] },
      { position: [1.9, 0.6, 0.9], rotation: [0.15, -0.4, -0.1], size: [1.3, 0.85] },
      { position: [-0.6, -0.2, 1.2], rotation: [-0.35, 0.2, 0.25], size: [1.05, 0.68] },
      { position: [1.1, -0.8, -0.3], rotation: [0.25, -0.7, 0.05], size: [0.9, 0.58] },
      { position: [-1.8, -1.1, -0.5], rotation: [-0.1, 0.6, -0.2], size: [1.1, 0.7] },
      { position: [0.2, -1.7, 0.7], rotation: [0.4, 0.1, 0.15], size: [0.85, 0.55] },
      { position: [-0.4, 0.4, -1.4], rotation: [0.05, -0.3, 0.3], size: [1.0, 0.65] },
    ];

    const panels: THREE.Group[] = [];
    for (const def of PANELS) {
      const panel = new THREE.Group();
      panel.position.set(...def.position);
      panel.rotation.set(...def.rotation);

      const geometry = new THREE.PlaneGeometry(def.size[0], def.size[1]);
      const fillMaterial = new THREE.MeshBasicMaterial({
        color: muteColor,
        transparent: true,
        opacity: 0.035,
        side: THREE.DoubleSide,
        depthWrite: false,
      });
      const fill = new THREE.Mesh(geometry, fillMaterial);
      panel.add(fill);
      disposables.push(geometry, fillMaterial);

      const edgesGeometry = new THREE.EdgesGeometry(geometry);
      const edgesMaterial = new THREE.LineBasicMaterial({
        color: lineColor,
        transparent: true,
        opacity: 0.55,
      });
      const edges = new THREE.LineSegments(edgesGeometry, edgesMaterial);
      panel.add(edges);
      disposables.push(edgesGeometry, edgesMaterial);

      cluster.add(panel);
      panels.push(panel);
    }

    // Foreign-key-style connectors between panel centres. One (only one)
    // carries the brand accent, matching the app's single-accent rule.
    const CONNECTIONS: Array<[number, number]> = [
      [0, 1],
      [1, 2],
      [0, 3],
      [3, 4],
      [4, 2],
      [3, 5],
      [5, 6],
      [0, 7],
    ];
    const ACCENT_CONNECTION_INDEX = 2;

    CONNECTIONS.forEach(([a, b], index) => {
      const points = [panels[a].position.clone(), panels[b].position.clone()];
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const isAccent = index === ACCENT_CONNECTION_INDEX;
      const material = new THREE.LineBasicMaterial({
        color: isAccent ? brandColor : lineColor,
        transparent: true,
        opacity: isAccent ? 0.85 : 0.3,
      });
      const line = new THREE.Line(geometry, material);
      cluster.add(line);
      disposables.push(geometry, material);
    });

    const pointer = { x: 0, y: 0 };
    const onPointerMove = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      pointer.y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
    };
    window.addEventListener('pointermove', onPointerMove, { passive: true });

    const fit = (width: number, height: number) => {
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    fit(host.clientWidth, host.clientHeight);

    const resizeObserver = new ResizeObserver(([entry]) => {
      fit(entry.contentRect.width, entry.contentRect.height);
    });
    resizeObserver.observe(host);

    // Base rotation: one full turn roughly every 52s — barely perceptible,
    // atmospheric. Pointer tilt rides on top via a critically-damped spring
    // (borrowed idea from the reference scene, simplified to two axes) so it
    // eases toward the pointer rather than snapping to it.
    const FULL_TURN_SECONDS = 52;
    const tilt = { x: 0, y: 0, vx: 0, vy: 0 };
    let frame = 0;
    let onScreen = true;
    let last = performance.now();
    let baseAngle = 0;

    const running = () => onScreen && document.visibilityState === 'visible';

    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.05);
      last = now;

      baseAngle += ((Math.PI * 2) / FULL_TURN_SECONDS) * dt;

      const targetX = -pointer.y * 0.09;
      const targetY = pointer.x * 0.12;
      const stiffness = 42;
      const damping = 11;
      tilt.vx += (targetX - tilt.x) * stiffness * dt - tilt.vx * damping * dt;
      tilt.vy += (targetY - tilt.y) * stiffness * dt - tilt.vy * damping * dt;
      tilt.x += tilt.vx * dt;
      tilt.y += tilt.vy * dt;

      cluster.rotation.y = baseAngle + tilt.y;
      cluster.rotation.x = tilt.x;

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

    // Paint once up front so a backgrounded tab doesn't start with an empty canvas.
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
  }, [onUnavailable]);

  return <div ref={hostRef} aria-hidden className="absolute inset-0" />;
}

/**
 * Reads a `--token` CSS custom property (as returned by
 * `getComputedStyle(...).getPropertyValue`) into a `THREE.Color`. Handles the
 * `#rrggbb` and `rgba()/rgb()` forms this app's tokens use — alpha is
 * dropped since `THREE.Color` carries no alpha channel; every material that
 * needs transparency sets its own `opacity` instead. Falls back to
 * `fallbackHex` if parsing fails, so a missing or unexpected token never
 * throws.
 */
function parseCssColor(raw: string, fallbackHex: string): THREE.Color {
  const value = raw.trim();
  if (!value) return new THREE.Color(fallbackHex);

  if (value.startsWith('#')) {
    // Chromium's computed-style serializer turns `rgba(10,10,10,0.15)` into
    // 8-digit hex (`#0a0a0a26`) rather than echoing the rgba() form back —
    // THREE.Color only parses 3/6-digit hex, so the trailing alpha pair is
    // dropped here (opacity is applied separately via each material).
    const hex = value.length === 9 ? value.slice(0, 7) : value.length === 5 ? value.slice(0, 4) : value;
    try {
      return new THREE.Color(hex);
    } catch {
      return new THREE.Color(fallbackHex);
    }
  }

  const match = value.match(/rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i);
  if (match) {
    const [, r, g, b] = match;
    return new THREE.Color(
      Number(r) / 255,
      Number(g) / 255,
      Number(b) / 255,
    );
  }

  try {
    return new THREE.Color(value);
  } catch {
    return new THREE.Color(fallbackHex);
  }
}

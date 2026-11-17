import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { AdvancedParameters } from './advanced-parameters.jsx';

const EASE = 'cubic-bezier(.22, .68, .2, 1)';

function useReducedMotion() {
    const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
    useEffect(() => {
        const preference = matchMedia('(prefers-reduced-motion: reduce)');
        const update = () => setReduced(preference.matches);
        preference.addEventListener('change', update);
        return () => preference.removeEventListener('change', update);
    }, []);
    return reduced;
}

function ModelModeSwitch({ reduced }) {
    const [mode, setMode] = useState(() => document.querySelector('[data-model-mode][aria-pressed="true"]')?.dataset.modelMode || 'predefined');
    const [disabled, setDisabled] = useState(() => Boolean(document.querySelector('[data-model-mode]')?.disabled));
    const selector = useRef(null);
    const indicator = useRef(null);
    const previousMode = useRef(mode);

    useEffect(() => {
        const onMode = event => setMode(event.detail.mode);
        const onDisabled = event => setDisabled(event.detail.disabled);
        window.addEventListener('stimmas:model-mode', onMode);
        window.addEventListener('stimmas:controls-disabled', onDisabled);
        return () => {
            window.removeEventListener('stimmas:model-mode', onMode);
            window.removeEventListener('stimmas:controls-disabled', onDisabled);
        };
    }, []);

    useLayoutEffect(() => {
        let animation;
        const placeIndicator = () => {
            const active = selector.current?.querySelector(`[data-model-mode="${mode}"]`);
            const pill = indicator.current;
            if (!active || !pill) return;
            const oldLeft = pill.style.left;
            const oldWidth = pill.style.width;
            const left = `${active.offsetLeft}px`;
            const width = `${active.offsetWidth}px`;
            animation?.cancel();
            Object.assign(pill.style, { left, width, opacity: '1' });
            if (!reduced && oldLeft && oldLeft !== left) {
                animation = pill.animate([{ left: oldLeft, width: oldWidth }, { left, width }], { duration: 220, easing: EASE });
            }
        };
        placeIndicator();
        const resize = new ResizeObserver(placeIndicator);
        resize.observe(selector.current);
        return () => { resize.disconnect(); animation?.cancel(); };
    }, [mode, reduced]);

    useEffect(() => {
        if (mode === previousMode.current || reduced) {
            previousMode.current = mode;
            return;
        }
        previousMode.current = mode;
        const animations = Array.from(document.querySelectorAll('.model-configuration-grid input:not([hidden]), .model-configuration-grid select:not([hidden])'), (field, index) =>
            field.animate([{ opacity: .55, transform: 'translateY(4px)' }, { opacity: 1, transform: 'translateY(0)' }], {
                duration: 200, delay: index * 25, easing: EASE
            })
        );
        return () => animations.forEach(animation => animation.cancel());
    }, [mode, reduced]);

    return (
        <div ref={selector} className="model-mode-selector is-react" role="group" aria-label="Model setup mode">
            <span ref={indicator} className="model-mode-indicator" aria-hidden="true" />
            {[
                ['predefined', 'Predefined Models', 'fa-layer-group'],
                ['custom', 'Custom Model', 'fa-code']
            ].map(([value, label, icon]) => (
                <button key={value} type="button" id={`${value}-model-mode`} data-model-mode={value}
                    className={`model-mode-button${mode === value ? ' is-active' : ''}`}
                    aria-pressed={mode === value} disabled={disabled}
                    onClick={() => window.setModelConfigurationMode(value)}>
                    <i className={`fas ${icon}`} aria-hidden="true" />{label}
                </button>
            ))}
        </div>
    );
}

function PageMotion({ reduced }) {
    useEffect(() => {
        document.documentElement.dataset.uiMotion = reduced ? 'reduced' : 'ready';
        if (reduced) return;
        const animations = new Set();
        const animate = (element, frames, duration = 240, delay = 0) => {
            if (!element?.isConnected) return;
            const animation = element.animate(frames, { duration, delay, easing: EASE });
            animations.add(animation);
            animation.finished.catch(() => {}).finally(() => animations.delete(animation));
        };
        const entrance = [{ opacity: .55, transform: 'translateY(8px)' }, { opacity: 1, transform: 'translateY(0)' }];
        const sections = new IntersectionObserver(entries => {
            entries.filter(entry => entry.isIntersecting).forEach((entry, index) => {
                // Leave the header steady and keep help panels outside transforms.
                animate(entry.target, [{ opacity: .65 }, { opacity: 1 }], 320, Math.min(index * 40, 80));
                sections.unobserve(entry.target);
            });
        }, { threshold: .06 });
        document.querySelectorAll('.settings-section, .agent-logs-section').forEach(section => sections.observe(section));

        const rows = new MutationObserver(records => {
            records.forEach(record => record.addedNodes.forEach(node => {
                if (!(node instanceof Element)) return;
                if (node.matches('.item-container')) animate(node, entrance, 220);
                else if (node.matches('tr')) animate(node, [{ opacity: .35 }, { opacity: 1 }], 180);
            }));
        });
        document.querySelectorAll('#items-container, #agent2PropertiesTable tbody, #agent3PropertiesTable tbody').forEach(container =>
            rows.observe(container, { childList: true, subtree: true })
        );

        const latestEvents = new WeakMap();
        const logUpdates = new MutationObserver(records => {
            new Set(records.map(record => record.target)).forEach(log => {
                const latest = log.lastElementChild;
                if (!latest?.matches('.timeline-event')) return;
                const signature = latest.textContent;
                if (latestEvents.get(log) === signature) return;
                latestEvents.set(log, signature);
                animate(latest, [{ opacity: .45 }, { opacity: 1 }], 180);
            });
        });
        document.querySelectorAll('.log-content').forEach(log => logUpdates.observe(log, { childList: true }));

        const onPress = event => {
            const button = event.target.closest('button');
            if (button && !button.disabled && event.button === 0) {
                animate(button, [{ transform: 'scale(1)' }, { transform: 'scale(.985)', offset: .45 }, { transform: 'scale(1)' }], 150);
            }
        };
        const onHelp = event => {
            const info = event.target.closest('.tooltip.info-icon');
            if (!info || (event.relatedTarget instanceof Node && info.contains(event.relatedTarget))) return;
            animate(info.querySelector('.tooltip-text'), [{ opacity: .2 }, { opacity: 1 }], 150);
        };
        document.addEventListener('pointerdown', onPress);
        document.addEventListener('pointerover', onHelp);
        document.addEventListener('focusin', onHelp);
        return () => {
            sections.disconnect(); rows.disconnect(); logUpdates.disconnect();
            document.removeEventListener('pointerdown', onPress);
            document.removeEventListener('pointerover', onHelp);
            document.removeEventListener('focusin', onHelp);
            animations.forEach(animation => animation.cancel());
        };
    }, [reduced]);
    return null;
}

function HeaderBackgroundMotion({ reduced }) {
    useLayoutEffect(() => {
        const header = document.querySelector('.header-container');
        if (!header) return;
        if (reduced) {
            header.dataset.backgroundMotion = 'reduced';
            return;
        }
        const waves = Array.from(header.querySelectorAll('.header-wave-layer'), (wave, index) => {
            const direction = index === 0 ? 1 : -1;
            return wave.animate([
                { transform: `translate3d(${-64 * direction}px, 4px, 0)` },
                { transform: `translate3d(${64 * direction}px, -4px, 0)` }
            ], {
                duration: (index === 0 ? 6500 : 8500) / 1.5,
                direction: 'alternate',
                iterations: Infinity,
                easing: 'cubic-bezier(.45, 0, .55, 1)'
            });
        });
        const bounds = header.getBoundingClientRect();
        let inView = bounds.bottom > 0 && bounds.top < window.innerHeight;
        const syncPlayback = () => {
            const running = inView && !document.hidden;
            waves.forEach(animation => running ? animation.play() : animation.pause());
            header.dataset.backgroundMotion = running ? 'running' : 'paused';
        };
        const visibility = new IntersectionObserver(([entry]) => {
            inView = entry.isIntersecting;
            syncPlayback();
        });
        visibility.observe(header);
        document.addEventListener('visibilitychange', syncPlayback);
        syncPlayback();
        return () => {
            visibility.disconnect();
            document.removeEventListener('visibilitychange', syncPlayback);
            waves.forEach(animation => animation.cancel());
            delete header.dataset.backgroundMotion;
        };
    }, [reduced]);
    return null;
}

function ProgressMotion({ reduced }) {
    const [progress, setProgress] = useState(null);
    useEffect(() => {
        const update = event => setProgress(event.detail);
        window.addEventListener('stimmas:progress', update);
        return () => window.removeEventListener('stimmas:progress', update);
    }, []);
    useEffect(() => {
        if (!progress || reduced || progress.value === 0 || progress.value === progress.previous) return;
        const bar = document.getElementById('progress_bar');
        const animation = bar.animate([{ width: `${progress.previous}%` }, { width: `${progress.value}%` }], { duration: 380, easing: EASE });
        return () => animation.cancel();
    }, [progress, reduced]);
    return null;
}

function InterfaceEnhancements() {
    const reduced = useReducedMotion();
    return <><ModelModeSwitch reduced={reduced} /><PageMotion reduced={reduced} /><HeaderBackgroundMotion reduced={reduced} /><ProgressMotion reduced={reduced} /></>;
}

createRoot(document.getElementById('model-mode-root')).render(<InterfaceEnhancements />);

createRoot(document.getElementById('advanced-parameters-root')).render(<AdvancedParameters />);

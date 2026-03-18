/**
 * ECharts wrapper — platform-specific.
 * Web: vanilla echarts.init() on a div (dynamic import to avoid SSR crash)
 * Mobile: @wuba/react-native-echarts SvgChart
 * Falls back to null if echarts is not installed.
 */
import React, { useRef, useEffect, useState, memo } from 'react';
import { Platform, View, type ViewStyle } from 'react-native';

interface EChartsWrapperProps {
    option: object;
    style?: ViewStyle;
    notMerge?: boolean;
    width?: number;
    height?: number;
}

// ============================================================
// Mobile-only: static require (tree-shaken on web)
// ============================================================

let echartsStatic: any = null;
let SvgChart: any = null;
let SVGRenderer: any = null;

if (Platform.OS !== 'web') {
    try {
        echartsStatic = require('echarts');
    } catch {
        // echarts not installed
    }
    try {
        const wuba = require('@wuba/react-native-echarts');
        SvgChart = wuba.SvgChart;
        SVGRenderer = wuba.SVGRenderer;
        if (echartsStatic && SVGRenderer) {
            echartsStatic.use([SVGRenderer]);
        }
    } catch {
        // @wuba/react-native-echarts not installed
    }
}

// ============================================================
// Web: dynamic echarts loaded via import() in useEffect
// ============================================================

let _echartsWeb: any = null; // cached after first load

/** Check if ECharts is available */
export const isEChartsAvailable = (): boolean => {
    if (Platform.OS === 'web') {
        // On web, always return true — echarts loads dynamically in useEffect.
        // buildEChartsOption() doesn't need echarts itself, so DataChart can
        // compute the option and pass it to us.
        return true;
    }
    return !!(echartsStatic && SvgChart);
};

// ============================================================
// Component
// ============================================================

const EChartsWrapperInner: React.FC<EChartsWrapperProps> = ({
    option,
    style,
    notMerge = true,
    width,
    height = 300,
}) => {
    // --- Hooks (called unconditionally to satisfy Rules of Hooks) ---
    const containerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<any>(null);
    const svgRef = useRef<any>(null);
    const [webReady, setWebReady] = useState(!!_echartsWeb);

    // Web: dynamically load echarts on first mount
    useEffect(() => {
        if (Platform.OS !== 'web') return;
        if (_echartsWeb) { setWebReady(true); return; }

        let cancelled = false;
        (async () => {
            try {
                const mod = await import('echarts');
                _echartsWeb = (mod as any).default || mod;
                if (!cancelled) setWebReady(true);
            } catch (err) {
                console.error('Failed to load echarts:', err);
            }
        })();
        return () => { cancelled = true; };
    }, []);

    // Web: init/update chart
    useEffect(() => {
        if (Platform.OS !== 'web' || !_echartsWeb || !containerRef.current) return;

        try {
            if (!chartRef.current) {
                // Ensure container has dimensions before init
                const el = containerRef.current;
                chartRef.current = _echartsWeb.init(el);
            }
            chartRef.current.setOption(option, notMerge);
        } catch (err) {
            console.error('[ECharts] Failed to init/setOption:', err);
        }

        // Resize on window resize
        const handleResize = () => chartRef.current?.resize();
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
        };
    }, [option, notMerge, webReady]);

    // Web: dispose on unmount
    useEffect(() => {
        if (Platform.OS !== 'web') return;
        return () => {
            chartRef.current?.dispose();
            chartRef.current = null;
        };
    }, []);

    // Mobile: init/update chart
    useEffect(() => {
        if (Platform.OS === 'web' || !echartsStatic || !svgRef.current) return;

        const chart = echartsStatic.init(svgRef.current, 'light', {
            renderer: 'svg',
            width: width || 350,
            height,
        });
        chart.setOption(option);
        return () => chart?.dispose();
    }, [option, width, height]);

    // ===== WEB RENDER =====
    if (Platform.OS === 'web') {
        if (!webReady) {
            return (
                <View style={[{ width: width || '100%', height }, style]}>
                    {/* @ts-ignore */}
                    <div style={{
                        width: '100%',
                        height: '100%',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#9CA3AF',
                        fontSize: 13,
                    }}>
                        Loading Chart...
                    </div>
                </View>
            );
        }

        return (
            <View style={[{ width: width || '100%', height }, style]}>
                {/* @ts-ignore — div is web-only */}
                <div
                    ref={containerRef}
                    style={{
                        width: typeof width === 'number' ? width : '100%',
                        height: typeof height === 'number' ? height : 300,
                    }}
                />
            </View>
        );
    }

    // ===== MOBILE RENDER =====
    if (!echartsStatic || !SvgChart) return null;

    return (
        <View style={[{ width: width || '100%', height }, style]}>
            <SvgChart ref={svgRef} />
        </View>
    );
};

export const EChartsWrapper = memo(EChartsWrapperInner);
export default EChartsWrapper;

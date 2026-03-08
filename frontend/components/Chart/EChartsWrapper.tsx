/**
 * ECharts wrapper — platform-specific.
 * Web: custom wrapper using echarts.init() + useRef + useEffect
 * Mobile: @wuba/react-native-echarts SvgChart
 * Falls back to null if echarts is not installed.
 */
import React, { useRef, useEffect, memo } from 'react';
import { Platform, View, type ViewStyle } from 'react-native';

interface EChartsWrapperProps {
    option: object;
    style?: ViewStyle;
    notMerge?: boolean;
    width?: number;
    height?: number;
}

// Try to import echarts — graceful fallback if not installed
let echarts: any = null;
try {
    echarts = require('echarts');
} catch {
    // echarts not installed — wrapper will return null
}

// Try mobile SVG renderer
let SvgChart: any = null;
let SVGRenderer: any = null;
if (Platform.OS !== 'web') {
    try {
        const wuba = require('@wuba/react-native-echarts');
        SvgChart = wuba.SvgChart;
        SVGRenderer = wuba.SVGRenderer;
        if (echarts && SVGRenderer) {
            echarts.use([SVGRenderer]);
        }
    } catch {
        // @wuba/react-native-echarts not installed
    }
}

/** Check if ECharts is available */
export const isEChartsAvailable = (): boolean => {
    if (Platform.OS === 'web') return !!echarts;
    return !!(echarts && SvgChart);
};

const EChartsWrapperInner: React.FC<EChartsWrapperProps> = ({
    option,
    style,
    notMerge = true,
    width,
    height = 300,
}) => {
    // ===== WEB =====
    if (Platform.OS === 'web') {
        const containerRef = useRef<HTMLDivElement>(null);
        const chartRef = useRef<any>(null);

        useEffect(() => {
            if (!echarts || !containerRef.current) return;

            if (!chartRef.current) {
                chartRef.current = echarts.init(containerRef.current);
            }
            chartRef.current.setOption(option, notMerge);

            const handleResize = () => chartRef.current?.resize();
            window.addEventListener('resize', handleResize);

            return () => {
                window.removeEventListener('resize', handleResize);
            };
        }, [option, notMerge]);

        useEffect(() => {
            return () => {
                chartRef.current?.dispose();
                chartRef.current = null;
            };
        }, []);

        if (!echarts) return null;

        return (
            <View style={[{ width: width || '100%', height }, style]}>
                {/* @ts-ignore — div is web-only */}
                <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
            </View>
        );
    }

    // ===== MOBILE (React Native) =====
    if (!echarts || !SvgChart) return null;

    const svgRef = useRef<any>(null);

    useEffect(() => {
        let chart: any;
        if (svgRef.current) {
            chart = echarts.init(svgRef.current, 'light', {
                renderer: 'svg',
                width: width || 350,
                height,
            });
            chart.setOption(option);
        }
        return () => chart?.dispose();
    }, [option, width, height]);

    return (
        <View style={[{ width: width || '100%', height }, style]}>
            <SvgChart ref={svgRef} />
        </View>
    );
};

export const EChartsWrapper = memo(EChartsWrapperInner);
export default EChartsWrapper;

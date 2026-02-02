import React from 'react';
import { View, Text, Dimensions } from 'react-native';
import { BarChart, LineChart } from 'react-native-gifted-charts';
import { useColorScheme } from '@/hooks/use-color-scheme';

interface DataChartProps {
    data: Record<string, any>[];
}

export const DataChart = ({ data }: DataChartProps) => {
    const colorScheme = useColorScheme();
    const isDark = colorScheme === 'dark';
    const screenWidth = Dimensions.get('window').width;

    // 1. Validate Data
    // We require at least 2 data points to show a trend or comparison.
    if (!data || data.length < 2) return null;

    const keys = Object.keys(data[0]);

    // Heuristics
    const monthKey = keys.find(k => ['month', 'เดือน'].some(term => k.toLowerCase().includes(term)));
    const yearKey = keys.find(k => ['year', 'ปี', 'พ.ศ.', 'ค.ศ.'].some(term => k.toLowerCase().includes(term)));
    const labelKey = monthKey || keys.find(k => ['date', 'label', 'name', 'product'].some(term => k.toLowerCase().includes(term)));

    const valueKey = keys.find(k =>
        ['total', 'revenue', 'amount', 'count', 'value', 'price', 'cost', 'profit', 'รายได้', 'ยอดรวม', 'จำนวน'].some(term => k.toLowerCase().includes(term))
    );

    if (!valueKey) return null;

    // 2. Transform Data
    const chartData = data.map(item => {
        let label = '';
        if (monthKey && yearKey) {
            // Check if year is 4 digits (e.g., 2568, 2025)
            const yearStr = String(item[yearKey]);
            const shortYear = yearStr.length === 4 ? yearStr.slice(-2) : yearStr;
            label = `${item[monthKey]}/${shortYear}`;
        } else if (labelKey) {
            label = String(item[labelKey]);
        } else {
            label = String(Object.values(item)[0]); // Fallback
        }

        return {
            value: Number(item[valueKey]),
            label: label,
            frontColor: '#3B82F6',
            labelTextStyle: { color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 },
            // Tooltip data
            formattedValue: Number(item[valueKey]).toLocaleString('th-TH', { minimumFractionDigits: 2 }),
            dataPointText: '' // Hide default
        };
    });

    const isLineChart = chartData.length > 20;

    // Compact Y-Axis
    const formatYLabel = (val: string) => {
        const num = parseFloat(val);
        if (num >= 1_000_000_000) return (num / 1_000_000_000).toFixed(1) + 'B';
        if (num >= 1_000_000) return (num / 1_000_000).toFixed(1) + 'M';
        if (num >= 1_000) return (num / 1_000).toFixed(1) + 'K';
        return num.toString();
    };

    const maxValue = Math.max(...chartData.map(d => d.value));

    const renderTooltip = (item: any, index: number) => {
        if (!item) return null;
        const isRightSide = index > chartData.length / 2;
        const isHighValue = item.value > (maxValue * 0.8);

        return (
            <View
                className="bg-gray-900 dark:bg-white px-3 py-2 rounded-lg shadow-lg"
                style={{
                    position: 'absolute',
                    // Smart vertical positioning: If value is high, show tooltip BELOW the point
                    bottom: isHighValue ? undefined : 10,
                    top: isHighValue ? 20 : undefined,

                    // Smart horizontal positioning
                    left: isRightSide ? undefined : -30,
                    right: isRightSide ? -10 : undefined,
                    zIndex: 100,
                    minWidth: 120, // Ensure it has some width
                    alignItems: 'center'
                }}
            >
                <Text className="text-white dark:text-gray-900 text-xs font-bold mb-1 text-center">{item.label}</Text>
                <Text className="text-white dark:text-gray-900 text-xs text-center">{item.formattedValue} บาท</Text>
            </View>
        );
    };

    return (
        <View className="my-4 p-4 bg-white dark:bg-gray-800 rounded-2xl border border-gray-100 dark:border-gray-700 shadow-sm"
            style={{ overflow: 'visible' }}>
            <View className="flex-row justify-between items-center mb-6">
                <Text className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                    📈 แนวโน้ม{valueKey}
                </Text>
            </View>

            <View style={{ marginLeft: -10 }}>
                {isLineChart ? (
                    <LineChart
                        data={chartData}
                        color="#3B82F6"
                        thickness={2}
                        startFillColor="rgba(59, 130, 246, 0.3)"
                        endFillColor="rgba(59, 130, 246, 0.01)"
                        startOpacity={0.9}
                        endOpacity={0.2}
                        initialSpacing={20}
                        noOfSections={4}
                        yAxisTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 }}
                        xAxisLabelTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 }}
                        formatYLabel={formatYLabel}
                        hideDataPoints={false}
                        dataPointsColor="#3B82F6"
                        curved
                        areaChart
                        height={200}
                        width={screenWidth * 0.75}
                        isAnimated
                        pointerConfig={{
                            pointerStripUptoDataPoint: true,
                            pointerStripColor: 'lightgray',
                            pointerStripWidth: 2,
                            strokeDashArray: [2, 5],
                            pointerColor: 'lightgray',
                            radius: 4,
                            pointerLabelWidth: 100,
                            pointerLabelHeight: 120,
                            pointerComponent: (items: any) => {
                                if (!items || items.length === 0 || !items[0]) return null;
                                return renderTooltip(items[0], 0);
                            },
                        }}
                    />
                ) : (
                    <BarChart
                        data={chartData}
                        barWidth={22}
                        spacing={24}
                        roundedTop
                        roundedBottom
                        hideRules
                        xAxisThickness={0}
                        yAxisThickness={0}
                        yAxisTextStyle={{ color: isDark ? '#9CA3AF' : '#6B7280', fontSize: 10 }}
                        formatYLabel={formatYLabel}
                        noOfSections={4}
                        height={200}
                        width={screenWidth * 0.75}
                        isAnimated
                        frontColor={'#3B82F6'}
                        renderTooltip={renderTooltip}
                    />
                )}
            </View>
            <Text className="text-[10px] text-gray-400 dark:text-gray-500 text-center mt-2">
                * แตะที่กราฟเพื่อดูยอดเงิน
            </Text>
        </View>
    );
};

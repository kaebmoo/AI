import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { TechnicalAccordion } from './TechnicalAccordion';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { DataChart } from './DataChart';
import { DataTable } from './DataTable';
import { ConfidenceBadge, ConfidenceData } from './ConfidenceBadge';

export interface DataWarning {
    code: string;
    message: string;
    severity: 'info' | 'warning' | 'important';
}

export interface ChartConfig {
    category_column?: string;
    measure_column?: string;
    series_column?: string;
}

export interface Message {
    id: string | number;
    role: 'user' | 'assistant';
    content: string;
    sql?: string;
    executionTime?: number;
    warnings?: DataWarning[];
    data?: Record<string, any>[];  // Query result data
    confidence?: ConfidenceData;   // Confidence score
    visualization?: string;        // AI Recommended visualization
    chartConfig?: ChartConfig;     // AI Recommended chart columns
}

interface ChatBubbleProps {
    message: Message;
}

// Initial number of rows to show
const INITIAL_ROWS = 5;

export const ChatBubble = ({ message }: ChatBubbleProps) => {
    const isUser = message.role === 'user';
    const colorScheme = useColorScheme();
    const isDark = colorScheme === 'dark';

    // Premium Color Palette
    const colors = {
        userBg: '#2563EB', // Blue 600
        userText: '#FFFFFF',
        assistantBg: isDark ? '#1F2937' : '#FFFFFF', // Gray 800 : White
        assistantText: isDark ? '#E5E7EB' : '#1F2937', // Gray 200 : Gray 800
        assistantBorder: isDark ? '#374151' : '#E5E7EB', // Gray 700 : Gray 200
        codeBg: isDark ? '#111827' : '#F3F4F6', // Gray 900 : Gray 100
        accent: '#3B82F6', // Blue 500
    };

    const [showAllData, setShowAllData] = useState(false);

    const dataToShow = message.data
        ? (showAllData ? message.data : message.data.slice(0, INITIAL_ROWS))
        : [];
    const hasMoreData = message.data && message.data.length > INITIAL_ROWS;

    // Advanced Markdown Styles
    const markdownStyles = {
        body: {
            color: colors.assistantText,
            fontSize: 16,
            lineHeight: 26,
            fontFamily: 'System',
        },
        paragraph: {
            marginBottom: 12,
            marginTop: 4,
        },
        heading1: {
            fontSize: 24,
            fontWeight: '700',
            color: isDark ? '#F9FAFB' : '#111827',
            marginTop: 20,
            marginBottom: 10,
            lineHeight: 32,
        },
        heading2: {
            fontSize: 20,
            fontWeight: '600',
            color: isDark ? '#F3F4F6' : '#1F2937',
            marginTop: 16,
            marginBottom: 8,
            lineHeight: 28,
        },
        heading3: {
            fontSize: 18,
            fontWeight: '600',
            color: isDark ? '#E5E7EB' : '#374151',
            marginTop: 12,
            marginBottom: 6,
            lineHeight: 26,
        },
        code_inline: {
            backgroundColor: colors.codeBg,
            color: isDark ? '#E0E7FF' : '#374151',
            borderRadius: 6,
            borderWidth: 1,
            borderColor: isDark ? '#374151' : '#E5E7EB',
            fontFamily: 'Menlo', // Using system monospace
            fontSize: 14,
            paddingHorizontal: 4,
            paddingVertical: 2,
        },
        code_block: {
            backgroundColor: colors.codeBg,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: isDark ? '#374151' : '#E5E7EB',
            padding: 16,
            marginVertical: 12,
            fontFamily: 'Menlo',
            fontSize: 14,
            color: isDark ? '#E0E7FF' : '#1F2937',
        },
        fence: {
            backgroundColor: colors.codeBg,
            borderRadius: 12,
            borderWidth: 1,
            borderColor: isDark ? '#374151' : '#E5E7EB',
            padding: 16,
            marginVertical: 12,
            fontFamily: 'Menlo',
            fontSize: 14,
            color: isDark ? '#E0E7FF' : '#1F2937',
        },
        list_item: {
            marginVertical: 4,
        },
        bullet_list: {
            marginBottom: 12,
        },
        ordered_list: {
            marginBottom: 12,
        },
        link: {
            color: colors.accent,
            textDecorationLine: 'none',
            fontWeight: '500',
        },
        blockquote: {
            backgroundColor: isDark ? 'rgba(59, 130, 246, 0.1)' : '#EFF6FF',
            borderLeftColor: colors.accent,
            borderLeftWidth: 4,
            paddingHorizontal: 12,
            paddingVertical: 8,
            marginVertical: 8,
            borderRadius: 4,
        }
    };

    return (
        <View className={`mb-6 w-full flex-row ${isUser ? 'justify-end' : 'justify-start'}`}>
            <View
                className={`max-w-[88%] rounded-[20px] px-5 py-4 shadow-sm ${isUser
                    ? 'bg-blue-600 rounded-tr-md'
                    : 'bg-white dark:bg-gray-800 border-[0.5px] border-gray-200 dark:border-gray-700 rounded-tl-md shadow-slate-200/50 dark:shadow-none'
                    }`}
                style={!isUser ? {
                    shadowColor: '#000',
                    shadowOffset: { width: 0, height: 2 },
                    shadowOpacity: 0.05,
                    shadowRadius: 8,
                    elevation: 2,
                } : {}}
            >
                {isUser ? (
                    <Text className="text-white text-[16px] leading-[26px]">
                        {message.content}
                    </Text>
                ) : (
                    <View>
                        {/* Markdown Display */}
                        <Markdown
                            // @ts-ignore
                            style={markdownStyles}
                        >
                            {message.content}
                        </Markdown>

                        {/* Data Chart Visualization */}
                        {message.data && message.data.length > 0 && (
                            <DataChart
                                data={message.data}
                                visualization={message.visualization}
                                chartConfig={message.chartConfig}
                            />
                        )}

                        {/* Key Metric Visualization (Single Value) */}
                        {message.data && message.data.length === 1 && Object.keys(message.data[0]).length <= 2 && (
                            <View className="mt-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl p-4 border border-blue-100 dark:border-blue-800">
                                {Object.entries(message.data[0]).map(([key, value]) => (
                                    <View key={key} className="items-center">
                                        <Text className="text-sm text-gray-500 dark:text-gray-400 font-medium uppercase tracking-wide mb-1">
                                            {key}
                                        </Text>
                                        <Text className="text-3xl font-bold text-blue-700 dark:text-blue-300">
                                            {typeof value === 'number'
                                                ? value.toLocaleString('th-TH', { maximumFractionDigits: 2 })
                                                : String(value)}
                                        </Text>
                                    </View>
                                ))}
                            </View>
                        )}

                        {/* Query Result Data - Data Grid / Table */}
                        {message.data && message.data.length > 0 && (message.data.length > 1 || Object.keys(message.data[0]).length > 2) && (
                            <DataTable data={dataToShow} />
                        )}
                        {/* Show More/Less Button */}
                        {hasMoreData && (
                            <TouchableOpacity
                                onPress={() => setShowAllData(!showAllData)}
                                className="py-3 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 active:bg-gray-50 dark:active:bg-gray-700 transition"
                            >
                                <Text className="text-[13px] text-blue-600 dark:text-blue-400 text-center font-semibold">
                                    {showAllData
                                        ? '▲ ย่อข้อมูล'
                                        : `▼ แสดงทั้งหมด ${message.data.length} รายการ`}
                                </Text>
                            </TouchableOpacity>
                        )}
                    </View>
                )}

                {/* Data Warnings - Enhanced */}
                {message.warnings && message.warnings.length > 0 && (
                    <View className="mt-4 space-y-2">
                        {message.warnings.map((warning, index) => (
                            <View
                                key={index}
                                className={`flex-row p-3 rounded-xl border ${warning.severity === 'important'
                                    ? 'bg-red-50 dark:bg-red-900/10 border-red-100 dark:border-red-900/30'
                                    : warning.severity === 'warning'
                                        ? 'bg-amber-50 dark:bg-amber-900/10 border-amber-100 dark:border-amber-900/30'
                                        : 'bg-blue-50 dark:bg-blue-900/10 border-blue-100 dark:border-blue-900/30'
                                    }`}
                            >
                                <Text className="mr-3 text-base">
                                    {warning.severity === 'important' ? '⚠️' : warning.severity === 'warning' ? '📝' : 'ℹ️'}
                                </Text>
                                <Text
                                    className={`flex-1 text-sm font-medium leading-5 ${warning.severity === 'important'
                                        ? 'text-red-800 dark:text-red-200'
                                        : warning.severity === 'warning'
                                            ? 'text-amber-800 dark:text-amber-200'
                                            : 'text-blue-800 dark:text-blue-200'
                                        }`}
                                >
                                    {warning.message}
                                </Text>
                            </View>
                        ))}
                    </View>
                )}

                {/* Confidence Badge */}
                {message.confidence && (
                    <ConfidenceBadge confidence={message.confidence} />
                )}

                {/* Technical Details Accordion */}
                {/* Technical Details Accordion */}
                {message.sql && (
                    <View className="mt-2">
                        <TechnicalAccordion
                            sql={message.sql}
                            executionTime={message.executionTime}
                        />
                    </View>
                )}
            </View>
        </View>
    );
};

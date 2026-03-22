import React, { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { TechnicalAccordion } from './TechnicalAccordion';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { DataChart } from './DataChart';
import { DataTable } from './DataTable';
import { PivotDataView } from './PivotDataView';
import { ConfidenceBadge, ConfidenceData } from './ConfidenceBadge';
import { chatService, FeedbackRating, FeedbackCategory } from '@/services/chat';

export interface DataWarning {
    code: string;
    message: string;
    severity: 'info' | 'warning' | 'important';
}

export type { ChartConfig } from '../../types/chart';
import type { ChartConfig } from '../../types/chart';

export interface Message {
    id: string | number;
    chatId?: number;               // Backend chat_history.id (for feedback)
    role: 'user' | 'assistant';
    content: string;
    sql?: string;
    executionTime?: number;
    warnings?: DataWarning[];
    data?: Record<string, any>[];  // Query result data
    confidence?: ConfidenceData;   // Confidence score
    visualization?: string;        // AI Recommended visualization
    chartConfig?: ChartConfig;     // AI Recommended chart columns
    displayHint?: 'hierarchical' | 'crosstab' | 'flat'; // AI recommended table display mode
    hierarchyColumns?: string[];   // Ordered column names for hierarchical display (parent→child)
    question?: string;             // Original question (needed for training)
    feedbackRating?: FeedbackRating; // User's feedback (persisted)
}

interface ChatBubbleProps {
    message: Message;
    onTrain?: (question: string, sql: string) => Promise<void>;
}

// Initial number of rows to show
const INITIAL_ROWS = 5;

export const ChatBubble = ({ message, onTrain }: ChatBubbleProps) => {
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
    const [showPivot, setShowPivot] = useState(false);
    const [feedbackState, setFeedbackState] = useState<FeedbackRating | null>(message.feedbackRating || null);
    const [showCategoryPicker, setShowCategoryPicker] = useState(false);
    const [feedbackSubmitting, setFeedbackSubmitting] = useState(false);

    const FEEDBACK_CATEGORIES: { value: FeedbackCategory; label: string }[] = [
        { value: 'wrong_data', label: 'ข้อมูลไม่ถูกต้อง' },
        { value: 'incomplete', label: 'ข้อมูลไม่ครบถ้วน' },
        { value: 'sql_error', label: 'SQL ผิดพลาด' },
        { value: 'hard_to_understand', label: 'เข้าใจยาก' },
        { value: 'slow', label: 'ช้าเกินไป' },
        { value: 'other', label: 'อื่นๆ' },
    ];

    const handleFeedback = async (rating: FeedbackRating, category?: FeedbackCategory) => {
        if (!message.chatId || feedbackSubmitting) return;
        setFeedbackSubmitting(true);
        try {
            await chatService.submitFeedback(message.chatId, { rating, category });
            setFeedbackState(rating);
            setShowCategoryPicker(false);
        } catch (e) {
            console.warn('Feedback submission failed:', e);
        } finally {
            setFeedbackSubmitting(false);
        }
    };

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
            borderRadius: 8,
        },
        strong: {
            fontWeight: '700',
            color: isDark ? '#60A5FA' : '#2563EB', // Highlighting bold text with primary color for emphasis
        },
        em: {
            fontStyle: 'italic',
            color: isDark ? '#D1D5DB' : '#4B5563',
        },
        hr: {
            backgroundColor: isDark ? '#374151' : '#E5E7EB',
            height: 1,
            marginVertical: 16,
        },
        table: {
            borderWidth: 1,
            borderColor: isDark ? '#374151' : '#E5E7EB',
            borderRadius: 8,
        },
        thead: {
            backgroundColor: isDark ? '#1F2937' : '#F9FAFB',
        },
        th: {
            padding: 8,
            fontWeight: '600',
            color: isDark ? '#F3F4F6' : '#111827',
            borderBottomWidth: 1,
            borderColor: isDark ? '#374151' : '#E5E7EB',
        },
        td: {
            padding: 8,
            borderBottomWidth: 1,
            borderColor: isDark ? '#374151' : '#E5E7EB',
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
                    boxShadow: '0px 2px 8px rgba(0, 0, 0, 0.05)',
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

                        {/* Query Result Data - Data Grid / Table (ORIGINAL — always shown) */}
                        {message.data && message.data.length > 0 && (message.data.length > 1 || Object.keys(message.data[0]).length > 2) && (
                            <DataTable
                                data={dataToShow}
                                displayHint={message.displayHint}
                                hierarchyColumns={message.hierarchyColumns}
                            />
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
                                        : `▼ แสดงทั้งหมด ${message.data?.length || 0} รายการ`}
                                </Text>
                            </TouchableOpacity>
                        )}

                        {/* Pivot Tool — ADDITIVE, shown below original chart+table */}
                        {message.data && message.data.length > 2 && Object.keys(message.data[0]).length >= 2 && (
                            <View className="mt-2">
                                <TouchableOpacity
                                    onPress={() => setShowPivot(!showPivot)}
                                    className={`self-end mr-1 mb-1 flex-row items-center px-3 py-1.5 rounded-full border ${
                                        showPivot
                                            ? 'bg-blue-600 border-blue-600'
                                            : isDark
                                                ? 'bg-gray-700 border-gray-600'
                                                : 'bg-gray-100 border-gray-300'
                                    }`}
                                >
                                    <Text className={`text-xs font-semibold ${
                                        showPivot ? 'text-white' : isDark ? 'text-gray-300' : 'text-gray-600'
                                    }`}>
                                        {showPivot ? '✕ ปิด Pivot' : '⊞ เปิด Pivot Tool'}
                                    </Text>
                                </TouchableOpacity>
                                {showPivot && (
                                    <PivotDataView
                                        data={message.data}
                                        title={message.chartConfig?.title}
                                    />
                                )}
                            </View>
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

                {/* Feedback Buttons */}
                {!isUser && message.chatId && (
                    <View className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                        {feedbackState ? (
                            <View className="flex-row items-center">
                                <Text className="text-xs text-gray-400 dark:text-gray-500">
                                    {feedbackState === 'thumbs_up' ? '👍 ขอบคุณสำหรับ feedback' : '👎 ขอบคุณ เราจะปรับปรุงต่อไป'}
                                </Text>
                            </View>
                        ) : (
                            <View>
                                <View className="flex-row items-center gap-2">
                                    <Text className="text-xs text-gray-400 dark:text-gray-500 mr-1">คำตอบนี้เป็นอย่างไร?</Text>
                                    <TouchableOpacity
                                        onPress={() => handleFeedback('thumbs_up', 'perfect')}
                                        disabled={feedbackSubmitting}
                                        className="px-3 py-1.5 rounded-full bg-gray-50 dark:bg-gray-700 active:bg-green-50 dark:active:bg-green-900/20"
                                    >
                                        <Text className="text-sm">👍</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity
                                        onPress={() => setShowCategoryPicker(true)}
                                        disabled={feedbackSubmitting}
                                        className="px-3 py-1.5 rounded-full bg-gray-50 dark:bg-gray-700 active:bg-red-50 dark:active:bg-red-900/20"
                                    >
                                        <Text className="text-sm">👎</Text>
                                    </TouchableOpacity>
                                </View>
                                {showCategoryPicker && (
                                    <View className="mt-2 flex-row flex-wrap gap-1.5">
                                        {FEEDBACK_CATEGORIES.map((cat) => (
                                            <TouchableOpacity
                                                key={cat.value}
                                                onPress={() => handleFeedback('thumbs_down', cat.value)}
                                                disabled={feedbackSubmitting}
                                                className="px-2.5 py-1 rounded-full bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 active:bg-red-100"
                                            >
                                                <Text className="text-xs text-red-700 dark:text-red-300">{cat.label}</Text>
                                            </TouchableOpacity>
                                        ))}
                                    </View>
                                )}
                            </View>
                        )}
                    </View>
                )}

                {/* Technical Details Accordion */}
                {message.sql && (
                    <View className="mt-2">
                        <TechnicalAccordion
                            sql={message.sql}
                            executionTime={message.executionTime}
                            onTrain={
                                (onTrain && message.question)
                                    ? async (newSql) => await onTrain(message.question!, newSql)
                                    : undefined
                            }
                        />
                    </View>
                )}
            </View>
        </View>
    );
};

import React from 'react';
import { View, Text } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { TechnicalAccordion } from './TechnicalAccordion';
import { useColorScheme } from '@/hooks/use-color-scheme';

export interface DataWarning {
    code: string;
    message: string;
    severity: 'info' | 'warning' | 'important';
}

export interface Message {
    id: string | number;
    role: 'user' | 'assistant';
    content: string;
    sql?: string;
    executionTime?: number;
    warnings?: DataWarning[];
}

interface ChatBubbleProps {
    message: Message;
}

export const ChatBubble = ({ message }: ChatBubbleProps) => {
    const isUser = message.role === 'user';
    const colorScheme = useColorScheme();
    const markdownTextColor = colorScheme === 'dark' ? '#E5E7EB' : '#1F2937'; // gray-200 : gray-800

    return (
        <View className={`mb-4 w-full flex-row ${isUser ? 'justify-end' : 'justify-start'}`}>
            <View
                className={`max-w-[85%] rounded-2xl px-4 py-3 ${isUser
                    ? 'bg-blue-600 rounded-tr-none'
                    : 'bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-tl-none'
                    }`}
            >
                {isUser ? (
                    <Text className="text-white text-base leading-6">
                        {message.content}
                    </Text>
                ) : (
                    <View>
                        {/* Markdown Display */}
                        <Markdown
                            style={{
                                body: { color: markdownTextColor, fontSize: 16, lineHeight: 24 },
                                paragraph: { marginBottom: 10 },
                                // code_inline: { backgroundColor: '#F3F4F6', color: '#EF4444', borderRadius: 4, padding: 2 },
                            }}
                        >
                            {message.content}
                        </Markdown>

                        {/* Data Warnings */}
                        {message.warnings && message.warnings.length > 0 && (
                            <View className="mt-3 border-t border-gray-200 dark:border-gray-600 pt-3">
                                {message.warnings.map((warning, index) => (
                                    <View
                                        key={index}
                                        className={`flex-row items-start p-2 rounded-lg mb-2 ${
                                            warning.severity === 'important'
                                                ? 'bg-red-50 dark:bg-red-900/20'
                                                : warning.severity === 'warning'
                                                ? 'bg-amber-50 dark:bg-amber-900/20'
                                                : 'bg-blue-50 dark:bg-blue-900/20'
                                        }`}
                                    >
                                        <Text className="mr-2">
                                            {warning.severity === 'important' ? '⚠️' : warning.severity === 'warning' ? '📝' : 'ℹ️'}
                                        </Text>
                                        <Text
                                            className={`flex-1 text-sm ${
                                                warning.severity === 'important'
                                                    ? 'text-red-700 dark:text-red-300'
                                                    : warning.severity === 'warning'
                                                    ? 'text-amber-700 dark:text-amber-300'
                                                    : 'text-blue-700 dark:text-blue-300'
                                            }`}
                                        >
                                            {warning.message}
                                        </Text>
                                    </View>
                                ))}
                            </View>
                        )}

                        {/* Technical Details Accordion */}
                        {message.sql && (
                            <TechnicalAccordion
                                sql={message.sql}
                                executionTime={message.executionTime}
                            />
                        )}
                    </View>
                )}
            </View>
        </View>
    );
};

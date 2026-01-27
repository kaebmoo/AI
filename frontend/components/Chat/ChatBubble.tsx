import React from 'react';
import { View, Text } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { TechnicalAccordion } from './TechnicalAccordion';

export interface Message {
    id: string | number;
    role: 'user' | 'assistant';
    content: string;
    sql?: string;
    executionTime?: number;
}

interface ChatBubbleProps {
    message: Message;
}

export const ChatBubble = ({ message }: ChatBubbleProps) => {
    const isUser = message.role === 'user';

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
                                body: { color: '#1F2937', fontSize: 16, lineHeight: 24 }, // gray-800
                                paragraph: { marginBottom: 10 },
                                // code_inline: { backgroundColor: '#F3F4F6', color: '#EF4444', borderRadius: 4, padding: 2 },
                            }}
                        >
                            {message.content}
                        </Markdown>

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

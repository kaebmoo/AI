import React, { useState } from 'react';
import { View, Text, TouchableOpacity, TextInput, ActivityIndicator, Alert } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import SyntaxHighlighter from 'react-native-syntax-highlighter';
import { vs2015 } from 'react-syntax-highlighter/dist/esm/styles/hljs';

interface TechnicalAccordionProps {
    sql: string;
    executionTime?: number;
    onTrain?: (newSql: string) => Promise<void>;
}

export const TechnicalAccordion = ({ sql, executionTime, onTrain }: TechnicalAccordionProps) => {
    const [expanded, setExpanded] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editedSql, setEditedSql] = useState(sql);
    const [isTraining, setIsTraining] = useState(false);

    const handleSave = async () => {
        if (!onTrain) return;

        setIsTraining(true);
        try {
            await onTrain(editedSql);
            setIsEditing(false);
            Alert.alert("Success", "System trained with corrected SQL!");
        } catch (error) {
            Alert.alert("Error", "Failed to train system");
        } finally {
            setIsTraining(false);
        }
    };

    return (
        <View className="mt-2 border border-gray-200/80 dark:border-gray-700/80 rounded-xl overflow-hidden bg-gray-50/50 dark:bg-gray-900/30">
            <TouchableOpacity
                onPress={() => setExpanded(!expanded)}
                className="flex-row items-center justify-between p-3 bg-transparent"
            >
                <View className="flex-row items-center space-x-2">
                    <Ionicons name="code-slash-outline" size={14} color="#6B7280" />
                    <Text className="text-xs font-medium text-gray-500 dark:text-gray-400">
                        Technical Details {executionTime && `(${executionTime.toFixed(0)}ms)`}
                    </Text>
                </View>
                <Ionicons
                    name={expanded ? "chevron-up" : "chevron-down"}
                    size={14}
                    color="#6B7280"
                />
            </TouchableOpacity>

            {expanded && (
                <View className="bg-gray-900 px-3 py-2 border-t border-gray-200/50 dark:border-gray-700/50">
                    <View className="flex-row justify-between items-center mb-1">
                        <Text className="text-[10px] text-gray-500 font-mono uppercase tracking-wider">
                            SQL Query
                        </Text>
                        {onTrain && !isEditing && (
                            <TouchableOpacity onPress={() => setIsEditing(true)}>
                                <Text className="text-[10px] text-blue-400 font-medium">Fix & Train</Text>
                            </TouchableOpacity>
                        )}
                    </View>

                    {isEditing ? (
                        <View>
                            <TextInput
                                value={editedSql}
                                onChangeText={setEditedSql}
                                multiline
                                style={{
                                    fontFamily: 'Menlo',
                                    fontSize: 12,
                                    color: '#E0E7FF',
                                    backgroundColor: '#1F2937',
                                    padding: 8,
                                    borderRadius: 4,
                                    minHeight: 100
                                }}
                            />
                            <View className="flex-row justify-end space-x-2 mt-2">
                                <TouchableOpacity
                                    onPress={() => setIsEditing(false)}
                                    className="px-3 py-1 bg-gray-700 rounded mr-2"
                                    disabled={isTraining}
                                >
                                    <Text className="text-white text-xs">Cancel</Text>
                                </TouchableOpacity>
                                <TouchableOpacity
                                    onPress={handleSave}
                                    className="px-3 py-1 bg-blue-600 rounded flex-row items-center"
                                    disabled={isTraining}
                                >
                                    {isTraining && <ActivityIndicator size="small" color="white" className="mr-1" />}
                                    <Text className="text-white text-xs">Save & Train</Text>
                                </TouchableOpacity>
                            </View>
                        </View>
                    ) : (
                        <SyntaxHighlighter
                            language='sql'
                            style={vs2015}
                            fontSize={12}
                            highlighter={"hljs"}
                            customStyle={{ padding: 0, backgroundColor: 'transparent' }}
                        >
                            {sql}
                        </SyntaxHighlighter>
                    )}
                </View>
            )}
        </View>
    );
};

import React, { useState, useRef, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, FlatList, KeyboardAvoidingView, Platform, ActivityIndicator, Alert, SafeAreaView } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ModelSelector } from '../../components/Chat/ModelSelector';
import { ContextSelector, ContextBadge, DataContext } from '../../components/Chat/ContextSelector';
import { ChatBubble, Message } from '../../components/Chat/ChatBubble';
import { chatService } from '../../services/chat';
import { contextService } from '../../services/context';
import { useAuth } from '../../context/AuthContext';

export default function ChatScreen() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState(''); // Let ModelSelector auto-select default from API
  const [context, setContext] = useState<DataContext>('auto'); // Default: auto-detect
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const flatListRef = useRef<FlatList>(null);
  const { signOut } = useAuth();

  // Initial greeting
  useEffect(() => {
    setMessages([
      {
        id: 'init',
        role: 'assistant',
        content: 'สวัสดีครับ ผมคือผู้ช่วยอัจฉริยะสำหรับข้อมูลด้านการเงิน NT\n\nสามารถถามข้อมูลได้หลายประเภท เช่น :\n- รายได้ (Revenue): รายได้แยกตามกลุ่มธุรกิจ/กลุ่มบริการ/บริการ/หน่วยงาน\n- ค่าใช้จ่าย (Expense): หมวดบัญชี, หน่วยงาน\n\nเลือกโหมด Auto เพื่อให้ระบบตรวจจับอัตโนมัติ หรือเลือกประเภทข้อมูลเองได้ครับ'
      }
    ])
  }, []);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now(),
      role: 'user',
      content: input.trim(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await chatService.sendMessage({
        question: userMessage.content,
        conversation_id: conversationId,
        provider: provider,
        context: context === 'auto' ? undefined : context  // undefined = auto-detect on backend
      });

      setConversationId(response.conversation_id);

      const aiMessage: Message = {
        id: response.id,
        role: 'assistant',
        content: response.answer,
        sql: response.sql_query,
        question: response.question, // Pass original question for training context
        executionTime: response.execution_time_ms,
        warnings: response.warnings,
        data: response.data,
        confidence: response.confidence as any,           // Confidence score from validation MCP
        visualization: response.visualization,     // AI recommended visualization type
        chartConfig: response.chart_config         // AI recommended chart columns
      };

      setMessages((prev) => [...prev, aiMessage]);
    } catch (error: any) {
      const msg = error.response?.data?.detail || 'Failed to get response';
      Alert.alert('Error', msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Scroll to bottom when messages change
    setTimeout(() => {
      flatListRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, [messages]);

  const handleTrain = async (question: string, sql: string) => {
    try {
      await chatService.train({
        question,
        sql,
        context: context === 'auto' ? undefined : context
      });
      // Optional: Refresh context or give visual feedback handled by component
    } catch (error) {
      console.error("Training error:", error);
      throw error; // Let component handle error alert
    }
  };

  return (
    <SafeAreaView className="flex-1 bg-gray-50 dark:bg-gray-900">
      <View className="flex-1 w-full max-w-4xl mx-auto">
        {/* Header */}
        <View className="px-4 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 shadow-sm z-10 w-full">
          <View className="flex-row items-center justify-between">
            <View>
              <Text className="text-lg font-bold text-gray-900 dark:text-white">NT AI Assistant</Text>
              <Text className="text-xs text-gray-500 dark:text-gray-400">Powered by Agentic AI</Text>
            </View>
            <View className="flex-row items-center gap-2">
              <ContextBadge context={context} />
              <TouchableOpacity onPress={signOut}>
                <Ionicons name="log-out-outline" size={24} color="#EF4444" />
              </TouchableOpacity>
            </View>
          </View>
          {/* Selectors Row */}
          <View className="flex-row items-center gap-2 mt-2">
            <ContextSelector context={context} onSelect={setContext} />
            <ModelSelector provider={provider} onSelect={setProvider} />
          </View>
        </View>

        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 0}
          className="flex-1"
        >
          <FlatList
            ref={flatListRef}
            data={messages}
            keyExtractor={(item) => item.id.toString()}
            renderItem={({ item }) => (
              <ChatBubble
                message={item}
                onTrain={handleTrain}
              />
            )}
            contentContainerStyle={{ padding: 16, paddingBottom: 20 }}
            className="flex-1"
          />

          {/* Disclaimer */}
          <View className="px-4 py-2 bg-amber-50 dark:bg-amber-900/20 border-t border-amber-200 dark:border-amber-800">
            <Text className="text-xs text-amber-700 dark:text-amber-300 text-center">
              หมายเหตุ: ข้อมูล "รายได้อื่น" เป็นรายได้ที่ยังไม่สุทธิ"
            </Text>
          </View>

          {/* Input Area */}
          <View className="p-4 bg-white dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800">
            <View className="flex-row items-center gap-2">
              <TextInput
                className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-full px-5 py-3 text-gray-900 dark:text-white max-h-24"
                placeholder="ถามข้อมูลรายได้หรือค่าใช้จ่าย..."
                placeholderTextColor="#9CA3AF"
                value={input}
                onChangeText={setInput}
                multiline
                returnKeyType="send"
                onSubmitEditing={handleSend} // Caution with multiline
              />
              <TouchableOpacity
                onPress={handleSend}
                disabled={loading || !input.trim()}
                className={`w-12 h-12 rounded-full items-center justify-center ${loading || !input.trim() ? 'bg-gray-200 dark:bg-gray-700' : 'bg-blue-600'
                  }`}
              >
                {loading ? (
                  <ActivityIndicator color={loading ? "#3B82F6" : "white"} />
                ) : (
                  <Ionicons name="send" size={20} color={loading || !input.trim() ? "#9CA3AF" : "white"} />
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </View>
    </SafeAreaView>
  );
}

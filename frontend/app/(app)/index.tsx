import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, FlatList,
  KeyboardAvoidingView, Platform, ActivityIndicator,
  SafeAreaView, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, router } from 'expo-router';
import { ModelSelector } from '../../components/Chat/ModelSelector';
import { ContextSelector, ContextBadge, DataContext } from '../../components/Chat/ContextSelector';
import { ChatBubble, Message } from '../../components/Chat/ChatBubble';
import { ErrorBoundary } from '../../components/ErrorBoundary';
import { ConversationList } from '../../components/Chat/ConversationList';
import { chatService } from '../../services/chat';
import { conversationService } from '../../services/conversation';
import { useAuth } from '../../context/AuthContext';

const GREETING_MESSAGE: Message = {
  id: 'init',
  role: 'assistant',
  content: 'สวัสดีครับ ผมคือผู้ช่วยอัจฉริยะสำหรับข้อมูลด้านการเงิน NT\n\nสามารถถามข้อมูลได้หลายประเภท เช่น :\n- รายได้ (Revenue): รายได้แยกตามกลุ่มธุรกิจ/กลุ่มบริการ/บริการ/หน่วยงาน\n- ค่าใช้จ่าย (Expense): หมวดบัญชี, หน่วยงาน\n\nเลือกโหมด Auto เพื่อให้ระบบตรวจจับอัตโนมัติ หรือเลือกประเภทข้อมูลเองได้ครับ',
};

const STATUS_LABELS: Record<string, string> = {
  started: 'กำลังเริ่มต้น...',
  analyzing: 'กำลังวิเคราะห์คำถาม...',
  generating: 'กำลังสร้าง SQL...',
  validating: 'กำลังตรวจสอบ SQL...',
  executing: 'กำลังดึงข้อมูล...',
  explaining: 'กำลังสรุปผล...',
};

/** Map a raw backend/provider error into an actionable Thai message.
 *  Alert.alert is a no-op on web, so errors are shown as an inline chat bubble
 *  instead — this keeps them from failing silently. */
const friendlyErrorMessage = (raw: string): string => {
  const s = String(raw || '');
  if (/RESOURCE_EXHAUSTED|spending cap|quota|\b429\b|exceeded/i.test(s)) {
    return '⚠️ **ระบบ AI ใช้โควตาหมดชั่วคราว** — ผู้ให้บริการ (เช่น Gemini) เกินวงเงิน/quota รายเดือน\n\nลองใหม่ภายหลัง หรือ**สลับผู้ให้บริการ AI** (Claude / Matcha) ที่ปุ่มเลือกโมเดลด้านบน';
  }
  if (/\b401\b|unauthorized|invalid api key|api key/i.test(s)) {
    return '⚠️ **เชื่อมต่อผู้ให้บริการ AI ไม่สำเร็จ** (API key ไม่ถูกต้อง/หมดอายุ) — กรุณาแจ้งผู้ดูแลระบบ';
  }
  if (/timeout|timed out|ETIMEDOUT|deadline/i.test(s)) {
    return '⚠️ **ระบบใช้เวลานานเกินไป** — กรุณาลองใหม่อีกครั้ง';
  }
  if (/\b5\d\d\b|internal server|bad gateway|unavailable/i.test(s)) {
    return '⚠️ **เซิร์ฟเวอร์มีปัญหาชั่วคราว** — กรุณาลองใหม่ภายหลัง';
  }
  return `⚠️ **เกิดข้อผิดพลาด**\n\n${s.slice(0, 400)}`;
};

export default function ChatScreen() {
  // URL params (Expo Router)
  const params = useLocalSearchParams<{ c?: string }>();

  const [messages, setMessages] = useState<Message[]>([GREETING_MESSAGE]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [statusText, setStatusText] = useState('');
  const [provider, setProvider] = useState('');
  const [context, setContext] = useState<DataContext>('auto');
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [sidebarVisible, setSidebarVisible] = useState(() =>
    Platform.OS === 'web' && typeof window !== 'undefined' && window.innerWidth >= 768
  );
  const [sidebarRefresh, setSidebarRefresh] = useState(0);
  const [restoringChat, setRestoringChat] = useState(false);
  const flatListRef = useRef<FlatList>(null);
  const inputRef = useRef<TextInput>(null);
  const { signOut } = useAuth();
  const { width } = useWindowDimensions();

  // Wide screen: sidebar defaults open, but user can toggle it
  const isWideScreen = Platform.OS === 'web' && width >= 768;

  // ---------------------------------------------------------------
  // Restore conversation from URL params on mount / param change
  // ---------------------------------------------------------------
  useEffect(() => {
    const urlConvId = params.c;
    if (urlConvId && urlConvId !== conversationId) {
      loadConversation(urlConvId);
    }
  }, [params.c]);

  const loadConversation = useCallback(async (convId: string) => {
    setRestoringChat(true);
    try {
      const conv = await conversationService.get(convId);
      setConversationId(convId);

      // Transform API messages to ChatBubble format
      const restored: Message[] = [GREETING_MESSAGE];
      for (const m of conv.messages) {
        // User message
        restored.push({
          id: `user-${m.id}`,
          role: 'user',
          content: m.question,
        });
        // Assistant message
        if (m.ai_response) {
          restored.push({
            id: m.id,
            chatId: m.id,
            role: 'assistant',
            content: m.ai_response,
            sql: m.generated_sql || undefined,
            question: m.question,
            executionTime: m.execution_time_ms,
          });
        }
      }
      setMessages(restored);
    } catch (err: any) {
      console.error('Failed to load conversation:', err);
      // If 404 or 403, go to new chat
      handleNewChat();
    } finally {
      setRestoringChat(false);
    }
  }, []);

  // ---------------------------------------------------------------
  // Update URL when conversationId changes
  // ---------------------------------------------------------------
  const updateUrl = useCallback((convId: string | undefined) => {
    if (Platform.OS === 'web') {
      if (convId) {
        const url = new URL(window.location.href);
        url.searchParams.set('c', convId);
        window.history.replaceState({}, '', url.toString());
      } else {
        const url = new URL(window.location.href);
        url.searchParams.delete('c');
        window.history.replaceState({}, '', url.toString());
      }
    }
  }, []);

  // ---------------------------------------------------------------
  // New Chat
  // ---------------------------------------------------------------
  const handleNewChat = useCallback(() => {
    setConversationId(undefined);
    setMessages([GREETING_MESSAGE]);
    setInput('');
    setStatusText('');
    setLoading(false);
    updateUrl(undefined);
    if (!isWideScreen) setSidebarVisible(false);
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [updateUrl, isWideScreen]);

  // ---------------------------------------------------------------
  // Select conversation from sidebar
  // ---------------------------------------------------------------
  const handleSelectConversation = useCallback((convId: string) => {
    if (convId === conversationId) {
      setSidebarVisible(false);
      return;
    }
    updateUrl(convId);
    loadConversation(convId);
    if (!isWideScreen) setSidebarVisible(false);
  }, [conversationId, updateUrl, loadConversation, isWideScreen]);

  // ---------------------------------------------------------------
  // Send message
  // ---------------------------------------------------------------
  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage: Message = {
      id: Date.now(),
      role: 'user',
      content: input.trim(),
    };

    const streamingId = `streaming-${Date.now()}`;
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setStatusText('กำลังเริ่มต้น...');

    try {
      await chatService.streamMessage(
        {
          question: userMessage.content,
          conversation_id: conversationId,
          provider: provider,
          context: context === 'auto' ? undefined : context,
        },
        {
          onStatus: (status, message) => {
            setStatusText(STATUS_LABELS[status] || message);
          },
          onDataReady: (data, sqlQuery) => {
            setStatusText('กำลังสรุปผล...');
            const previewMessage: Message = {
              id: streamingId,
              role: 'assistant',
              content: '⏳ กำลังสรุปผลลัพธ์...',
              sql: sqlQuery,
              data: data,
            };
            setMessages((prev) => [...prev, previewMessage]);
          },
          onAnswer: (response) => {
            // Update conversationId (first message creates the conversation)
            if (response.conversation_id && response.conversation_id !== conversationId) {
              setConversationId(response.conversation_id);
              updateUrl(response.conversation_id);
            }

            // Chart-only: update existing message's chart
            if (response.is_chart_only) {
              setMessages((prev) => {
                const updated = [...prev];
                for (let i = updated.length - 1; i >= 0; i--) {
                  if (updated[i].data && updated[i].data!.length > 0) {
                    updated[i] = {
                      ...updated[i],
                      data: response.data ?? updated[i].data,
                      visualization: response.visualization,
                      chartConfig: response.chart_config,
                    };
                    break;
                  }
                }
                return updated;
              });
              return;
            }

            const aiMessage: Message = {
              id: response.id ?? Date.now(),
              chatId: response.id,
              role: 'assistant',
              content: response.answer,
              sql: response.sql_query,
              question: response.question,
              executionTime: response.execution_time_ms,
              warnings: response.warnings,
              data: response.data,
              confidence: response.confidence as any,
              visualization: response.visualization,
              chartConfig: response.chart_config,
              displayHint: response.display_hint,
              hierarchyColumns: response.hierarchy_columns,
            };

            // Replace preview message or append
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === streamingId);
              if (idx >= 0) {
                const updated = [...prev];
                updated[idx] = aiMessage;
                return updated;
              }
              return [...prev, aiMessage];
            });
          },
          onDone: (_id, _convId) => {
            setStatusText('');
            // Refresh sidebar conversation list
            setSidebarRefresh((n) => n + 1);
          },
          onError: (error) => {
            showErrorBubble(error);
          },
        }
      );
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.message || 'Failed to get response';
      showErrorBubble(msg);
    } finally {
      setLoading(false);
      setStatusText('');
    }

    // Surface an error inline (Alert.alert is a no-op on web → would fail silently).
    // Replaces any "⏳ กำลังสรุปผล" preview so the chat never gets stuck.
    function showErrorBubble(raw: string) {
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: friendlyErrorMessage(raw),
      };
      setMessages((prev) => [...prev.filter((m) => m.id !== streamingId), errorMessage]);
      setStatusText('');
    }
  };

  // Scroll to bottom
  useEffect(() => {
    setTimeout(() => {
      flatListRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, [messages]);

  const handleTrain = async (question: string, sql: string) => {
    try {
      await chatService.train({
        question,
        sql,
        context: context === 'auto' ? undefined : context,
      });
    } catch (error) {
      console.error('Training error:', error);
      throw error;
    }
  };

  // ---------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------
  return (
    <SafeAreaView className="flex-1 bg-gray-50 dark:bg-gray-900">
      <View className="flex-1 flex-row">
        {/* Sidebar — default open on wide web, toggleable everywhere */}
        {sidebarVisible && (
          <>
            {/* Overlay for mobile */}
            {!isWideScreen && (
              <TouchableOpacity
                onPress={() => setSidebarVisible(false)}
                activeOpacity={1}
                className="absolute inset-0 z-20"
                style={{ backgroundColor: 'rgba(0,0,0,0.3)' }}
              />
            )}
            <View
              className={`z-30 ${isWideScreen ? '' : 'absolute left-0 top-0 bottom-0'}`}
              style={!isWideScreen ? { elevation: 10 } : undefined}
            >
              <ConversationList
                currentConversationId={conversationId}
                onSelectConversation={handleSelectConversation}
                onNewChat={handleNewChat}
                visible={sidebarVisible}
                onClose={() => setSidebarVisible(false)}
                refreshTrigger={sidebarRefresh}
              />
            </View>
          </>
        )}

        {/* Main chat area */}
        <View className="flex-1">
          <View className="flex-1 w-full max-w-5xl mx-auto">
            {/* Header */}
            <View className="px-4 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 shadow-sm z-10 w-full">
              <View className="flex-row items-center justify-between">
                <View className="flex-row items-center gap-2">
                  {/* Sidebar toggle / New Chat */}
                  <TouchableOpacity
                    onPress={() => setSidebarVisible(!sidebarVisible)}
                    className="w-9 h-9 rounded-lg items-center justify-center bg-gray-100 dark:bg-gray-800"
                  >
                    <Ionicons name={sidebarVisible ? 'close' : 'menu'} size={20} color="#6B7280" />
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={handleNewChat}
                    className="w-9 h-9 rounded-lg items-center justify-center bg-blue-600"
                  >
                    <Ionicons name="add" size={20} color="white" />
                  </TouchableOpacity>
                  <View>
                    <Text className="text-lg font-bold text-gray-900 dark:text-white">NT AI Assistant</Text>
                    <Text className="text-xs text-gray-500 dark:text-gray-400">Powered by Agentic AI</Text>
                  </View>
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

            {/* Loading overlay for conversation restore */}
            {restoringChat ? (
              <View className="flex-1 items-center justify-center">
                <ActivityIndicator size="large" color="#3B82F6" />
                <Text className="text-sm text-gray-500 dark:text-gray-400 mt-2">
                  กำลังโหลดสนทนา...
                </Text>
              </View>
            ) : (
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
                    // Per-message boundary: a crash in one bubble (bad chart/table
                    // data) shows a fallback for that message only, never blanks the app
                    <ErrorBoundary label="ChatBubble">
                      <ChatBubble message={item} onTrain={handleTrain} />
                    </ErrorBoundary>
                  )}
                  contentContainerStyle={{ padding: 16, paddingBottom: 20 }}
                  className="flex-1"
                />

                {/* Disclaimer */}
                <View className="px-4 py-2 bg-amber-50 dark:bg-amber-900/20 border-t border-amber-200 dark:border-amber-800">
                  <Text className="text-xs text-amber-700 dark:text-amber-300 text-center">
                    หมายเหตุ: ข้อมูล &quot;รายได้อื่น&quot; เป็นรายได้ที่ยังไม่สุทธิ
                  </Text>
                </View>

                {/* Status Text */}
                {loading && statusText ? (
                  <View className="px-4 py-2 bg-blue-50 dark:bg-blue-900/20 border-t border-blue-100 dark:border-blue-800">
                    <View className="flex-row items-center gap-2">
                      <ActivityIndicator size="small" color="#3B82F6" />
                      <Text className="text-xs text-blue-600 dark:text-blue-300 font-medium">
                        {statusText}
                      </Text>
                    </View>
                  </View>
                ) : null}

                {/* Input Area */}
                <View className="p-4 bg-white dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800">
                  <View className="flex-row items-center gap-2">
                    <TextInput
                      ref={inputRef}
                      className="flex-1 bg-gray-100 dark:bg-gray-800 rounded-full px-5 py-3 text-gray-900 dark:text-white max-h-24"
                      placeholder="ถามข้อมูลรายได้หรือค่าใช้จ่าย..."
                      placeholderTextColor="#9CA3AF"
                      value={input}
                      onChangeText={setInput}
                      multiline
                      returnKeyType="send"
                      onSubmitEditing={handleSend}
                    />
                    <TouchableOpacity
                      onPress={handleSend}
                      disabled={loading || !input.trim()}
                      className={`w-12 h-12 rounded-full items-center justify-center ${
                        loading || !input.trim()
                          ? 'bg-gray-200 dark:bg-gray-700'
                          : 'bg-blue-600'
                      }`}
                    >
                      {loading ? (
                        <ActivityIndicator color="#3B82F6" />
                      ) : (
                        <Ionicons
                          name="send"
                          size={20}
                          color={loading || !input.trim() ? '#9CA3AF' : 'white'}
                        />
                      )}
                    </TouchableOpacity>
                  </View>
                </View>
              </KeyboardAvoidingView>
            )}
          </View>
        </View>
      </View>
    </SafeAreaView>
  );
}

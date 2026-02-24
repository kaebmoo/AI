import React, { useState, useEffect } from 'react';
import {
    Card,
    Row,
    Col,
    Switch,
    Select,
    Button,
    Input,
    InputNumber,
    message,
    Spin,
    Alert,
    Typography,
    Divider,
    Space,
    Tooltip
} from 'antd';
import { SaveOutlined, ReloadOutlined, ClearOutlined, InfoCircleOutlined, DatabaseOutlined } from '@ant-design/icons';
import { adminService } from '../services/adminService';
import type { AIConfig, AIProvider, FeatureFlags } from '../services/adminService';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const Settings: React.FC = () => {
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const [aiConfig, setAiConfig] = useState<AIConfig | null>(null);
    const [providers, setProviders] = useState<AIProvider[]>([]);
    const [featureFlags, setFeatureFlags] = useState<FeatureFlags | null>(null);

    const [availableModels, setAvailableModels] = useState<Record<string, string[]>>({});

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            setLoading(true);
            setError(null);

            // Fetch AI config
            const configResponse = await adminService.getAIConfig();
            setAiConfig(configResponse.ai);
            setFeatureFlags(configResponse.features);

            // Fetch providers
            const providersData = await adminService.getProviders();
            setProviders(providersData);

            // Fetch available models for each provider
            const modelsData: Record<string, string[]> = {};
            for (const provider of ['claude', 'gemini', 'matcha']) {
                try {
                    const models = await adminService.getAvailableModels(provider);
                    modelsData[provider] = models;
                } catch (err) {
                    console.error(`Failed to fetch models for ${provider}:`, err);
                    modelsData[provider] = [];
                }
            }
            setAvailableModels(modelsData);

        } catch (err: any) {
            setError(err.message || 'Failed to load configuration');
            message.error('Failed to load configuration');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveAIConfig = async () => {
        if (!aiConfig) return;

        try {
            setSaving(true);
            setError(null);

            await adminService.updateAIConfig(aiConfig);

            message.success('AI configuration saved successfully!');

            // Refresh data
            await fetchData();

        } catch (err: any) {
            setError(err.message || 'Failed to save configuration');
            message.error('Failed to save configuration');
        } finally {
            setSaving(false);
        }
    };

    const handleToggleFeature = async (featureName: string, enabled: boolean) => {
        try {
            setError(null);

            await adminService.toggleFeature(featureName, enabled);

            setFeatureFlags(prev => prev ? { ...prev, [featureName]: enabled } : null);
            message.success(`Feature "${featureName}" ${enabled ? 'enabled' : 'disabled'}`);

        } catch (err: any) {
            setError(err.message || 'Failed to toggle feature');
            message.error('Failed to toggle feature');
        }
    };

    const handleClearCache = async () => {
        try {
            setError(null);

            await adminService.clearConfigCache();
            message.success('Configuration cache cleared!');

        } catch (err: any) {
            setError(err.message || 'Failed to clear cache');
            message.error('Failed to clear cache');
        }
    };

    const [rebuildingIndex, setRebuildingIndex] = useState(false);

    const handleRebuildKeywordIndex = async () => {
        try {
            setRebuildingIndex(true);
            setError(null);

            const result = await adminService.rebuildKeywordIndex();
            message.success(`Keyword index rebuilt: ${result.total_entries || 0} entries`);

        } catch (err: any) {
            setError(err.message || 'Failed to rebuild keyword index');
            message.error('Failed to rebuild keyword index');
        } finally {
            setRebuildingIndex(false);
        }
    };

    if (loading) {
        return (
            <div style={{ textAlign: 'center', marginTop: 100 }}>
                <Spin size="large" />
                <div style={{ marginTop: 16 }}>
                    <Text>Loading configuration...</Text>
                </div>
            </div>
        );
    }

    return (
        <div>
            <Title level={2}>Settings</Title>
            <Paragraph>Manage AI providers, models, and system features</Paragraph>

            {error && (
                <Alert
                    message="Error"
                    description={error}
                    type="error"
                    closable
                    onClose={() => setError(null)}
                    style={{ marginBottom: 24 }}
                />
            )}

            {/* AI Provider Configuration */}
            <Card
                title="AI Provider Configuration"
                style={{ marginBottom: 24 }}
                extra={
                    <Space>
                        <Button
                            icon={<ReloadOutlined />}
                            onClick={fetchData}
                        >
                            Reset
                        </Button>
                        <Button
                            type="primary"
                            icon={<SaveOutlined />}
                            onClick={handleSaveAIConfig}
                            loading={saving}
                        >
                            Save Configuration
                        </Button>
                    </Space>
                }
            >
                {aiConfig && (
                    <>
                        {/* Default Provider */}
                        <div style={{ marginBottom: 24 }}>
                            <Text strong>Default Provider</Text>
                            <Select
                                value={aiConfig.default_provider}
                                onChange={(value) => setAiConfig({ ...aiConfig, default_provider: value })}
                                style={{ width: '100%', marginTop: 8 }}
                            >
                                <Option value="claude">Claude (Anthropic)</Option>
                                <Option value="gemini">Gemini (Google)</Option>
                                <Option value="matcha">Matcha (NT Gateway)</Option>
                            </Select>
                        </div>

                        <Divider />

                        {/* Claude Settings */}
                        <Card
                            type="inner"
                            title="Claude (Anthropic)"
                            style={{ marginBottom: 16 }}
                            extra={
                                <Switch
                                    checked={aiConfig.claude_enabled}
                                    onChange={(checked) => setAiConfig({ ...aiConfig, claude_enabled: checked })}
                                />
                            }
                        >
                            <div style={{ marginBottom: 16 }}>
                                <Text>Model</Text>
                                <Select
                                    value={aiConfig.claude_model}
                                    onChange={(value) => setAiConfig({ ...aiConfig, claude_model: value })}
                                    disabled={!aiConfig.claude_enabled}
                                    style={{ width: '100%', marginTop: 8 }}
                                >
                                    {availableModels.claude?.map(model => (
                                        <Option key={model} value={model}>{model}</Option>
                                    ))}
                                </Select>
                            </div>

                            <Divider style={{ margin: '12px 0' }} />

                            {/* Extended Thinking */}
                            <Row justify="space-between" align="middle" style={{ marginBottom: 12 }}>
                                <Col>
                                    <Space>
                                        <Text strong>Extended Thinking</Text>
                                        <Tooltip title="Claude จะใช้ internal reasoning ก่อนตอบ — ช่วยให้ SQL แม่นยำขึ้นสำหรับคำถามซับซ้อน รองรับเฉพาะ claude-sonnet-4 และ claude-opus-4">
                                            <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                                        </Tooltip>
                                    </Space>
                                    <br />
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                        เพิ่มความแม่นยำ SQL (เพิ่ม cost และ latency)
                                    </Text>
                                </Col>
                                <Col>
                                    <Switch
                                        checked={aiConfig.claude_extended_thinking ?? false}
                                        onChange={(checked) => setAiConfig({ ...aiConfig, claude_extended_thinking: checked })}
                                        disabled={!aiConfig.claude_enabled}
                                    />
                                </Col>
                            </Row>

                            {aiConfig.claude_extended_thinking && (
                                <div>
                                    <Text>Thinking Budget (tokens)</Text>
                                    <Tooltip title="จำนวน token สำหรับ internal reasoning (1,024 – 100,000) ยิ่งมาก ยิ่งคิดลึก แต่ใช้เวลาและ cost มากขึ้น">
                                        <InfoCircleOutlined style={{ color: '#8c8c8c', marginLeft: 6 }} />
                                    </Tooltip>
                                    <InputNumber
                                        value={aiConfig.claude_thinking_budget_tokens ?? 8000}
                                        onChange={(value) => setAiConfig({ ...aiConfig, claude_thinking_budget_tokens: value ?? 8000 })}
                                        min={1024}
                                        max={100000}
                                        step={1000}
                                        disabled={!aiConfig.claude_enabled}
                                        style={{ width: '100%', marginTop: 8 }}
                                        formatter={(value) => `${value}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                                        parser={(value) => parseInt(value?.replace(/,/g, '') ?? '8000') as any}
                                    />
                                </div>
                            )}
                        </Card>

                        {/* Gemini Settings */}
                        <Card
                            type="inner"
                            title="Gemini (Google)"
                            style={{ marginBottom: 16 }}
                            extra={
                                <Switch
                                    checked={aiConfig.gemini_enabled}
                                    onChange={(checked) => setAiConfig({ ...aiConfig, gemini_enabled: checked })}
                                />
                            }
                        >
                            <div>
                                <Text>Model</Text>
                                <Select
                                    value={aiConfig.gemini_model}
                                    onChange={(value) => setAiConfig({ ...aiConfig, gemini_model: value })}
                                    disabled={!aiConfig.gemini_enabled}
                                    style={{ width: '100%', marginTop: 8 }}
                                >
                                    {availableModels.gemini?.map(model => (
                                        <Option key={model} value={model}>{model}</Option>
                                    ))}
                                </Select>
                            </div>
                        </Card>

                        {/* Matcha Settings */}
                        <Card
                            type="inner"
                            title="Matcha (NT Gateway)"
                            extra={
                                <Switch
                                    checked={aiConfig.matcha_enabled}
                                    onChange={(checked) => setAiConfig({ ...aiConfig, matcha_enabled: checked })}
                                />
                            }
                        >
                            <div style={{ marginBottom: 16 }}>
                                <Text>Model</Text>
                                <Select
                                    value={aiConfig.matcha_model}
                                    onChange={(value) => setAiConfig({ ...aiConfig, matcha_model: value })}
                                    disabled={!aiConfig.matcha_enabled}
                                    style={{ width: '100%', marginTop: 8 }}
                                >
                                    {availableModels.matcha?.map(model => (
                                        <Option key={model} value={model}>{model}</Option>
                                    ))}
                                </Select>
                            </div>
                            <div>
                                <Text>API URL</Text>
                                <Input
                                    value={aiConfig.matcha_api_url}
                                    onChange={(e) => setAiConfig({ ...aiConfig, matcha_api_url: e.target.value })}
                                    disabled={!aiConfig.matcha_enabled}
                                    placeholder="https://aigateway.ntictsolution.com/v1/chat/completions"
                                    style={{ marginTop: 8 }}
                                />
                            </div>
                        </Card>
                    </>
                )}
            </Card>

            {/* Feature Flags */}
            <Card title="Feature Flags" style={{ marginBottom: 24 }}>
                {featureFlags && (
                    <Row gutter={[16, 16]}>
                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Text strong>RAG Enabled</Text>
                                        <br />
                                        <Text type="secondary">Enable Retrieval-Augmented Generation</Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.rag_enabled}
                                            onChange={(checked) => handleToggleFeature('rag_enabled', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>

                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Text strong>Auto Context Detection</Text>
                                        <br />
                                        <Text type="secondary">Automatically detect context from questions</Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.auto_context_detection}
                                            onChange={(checked) => handleToggleFeature('auto_context_detection', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>

                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Text strong>Debug Mode</Text>
                                        <br />
                                        <Text type="secondary">Show debug information in responses</Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.debug_mode}
                                            onChange={(checked) => handleToggleFeature('debug_mode', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>

                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Text strong>Log Queries</Text>
                                        <br />
                                        <Text type="secondary">Save all generated SQL queries</Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.log_queries}
                                            onChange={(checked) => handleToggleFeature('log_queries', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>

                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Text strong>Collect Feedback</Text>
                                        <br />
                                        <Text type="secondary">Enable user feedback collection</Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.collect_feedback}
                                            onChange={(checked) => handleToggleFeature('collect_feedback', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>

                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Space>
                                            <Text strong>Two-Pass SQL Generation</Text>
                                            <Tooltip title="Pass 1: AI วิเคราะห์คำถามเป็น structured intent (JSON) → Pass 2: AI สร้าง SQL จาก intent — ลด retry, เพิ่มความแม่นยำ, debug ง่าย (เพิ่ม API call 1 ครั้ง)">
                                                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                                            </Tooltip>
                                        </Space>
                                        <br />
                                        <Text type="secondary">
                                            แยกขั้นตอนวิเคราะห์คำถาม (Pass 1) กับสร้าง SQL (Pass 2) เพิ่มความแม่นยำ
                                        </Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.two_pass_enabled}
                                            onChange={(checked) => handleToggleFeature('two_pass_enabled', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>

                        <Col span={24}>
                            <Card type="inner">
                                <Row justify="space-between" align="middle">
                                    <Col>
                                        <Space>
                                            <Text strong>Value Lookup</Text>
                                            <Tooltip title="ค้นหาค่าจริงในฐานข้อมูล (keyword index) ก่อนสร้าง SQL — ช่วยให้ AI ใช้ column/value ที่ถูกต้อง แต่อาจทำให้ AI สับสนถ้า semantic mapping ถูกต้องอยู่แล้ว">
                                                <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                                            </Tooltip>
                                        </Space>
                                        <br />
                                        <Text type="secondary">
                                            ค้น keyword จากคำถามใน DB แล้ว inject ค่าจริงเข้า prompt (ใช้เมื่อ semantic mapping ไม่ครอบคลุม)
                                        </Text>
                                    </Col>
                                    <Col>
                                        <Switch
                                            checked={featureFlags.value_lookup_enabled}
                                            onChange={(checked) => handleToggleFeature('value_lookup_enabled', checked)}
                                        />
                                    </Col>
                                </Row>
                            </Card>
                        </Col>
                    </Row>
                )}
            </Card>

            {/* Data & Cache Management */}
            <Card title="Data & Cache Management">
                <Row gutter={[16, 16]}>
                    <Col span={24}>
                        <Card type="inner">
                            <Row justify="space-between" align="middle">
                                <Col>
                                    <Space>
                                        <Text strong>Rebuild Keyword Index</Text>
                                        <Tooltip title="Scan ค่าจริงในฐานข้อมูล (SERVICE_GROUP, PRODUCT_NAME, BUSINESS_GROUP ฯลฯ) แล้วสร้าง index สำหรับ Smart Value Lookup — ช่วยให้ AI หาค่าที่ตรงกับ keyword ของผู้ใช้ได้">
                                            <InfoCircleOutlined style={{ color: '#8c8c8c' }} />
                                        </Tooltip>
                                    </Space>
                                    <br />
                                    <Text type="secondary">
                                        สร้าง keyword index ใหม่จากข้อมูลล่าสุด (กด rebuild เมื่อมีการอัพเดทข้อมูล)
                                    </Text>
                                </Col>
                                <Col>
                                    <Button
                                        icon={<DatabaseOutlined />}
                                        onClick={handleRebuildKeywordIndex}
                                        loading={rebuildingIndex}
                                    >
                                        Rebuild Index
                                    </Button>
                                </Col>
                            </Row>
                        </Card>
                    </Col>
                    <Col span={24}>
                        <Card type="inner">
                            <Row justify="space-between" align="middle">
                                <Col>
                                    <Text strong>Clear Configuration Cache</Text>
                                    <br />
                                    <Text type="secondary">ล้าง cache ค่า config เพื่อโหลดค่าล่าสุดจาก database</Text>
                                </Col>
                                <Col>
                                    <Button
                                        icon={<ClearOutlined />}
                                        onClick={handleClearCache}
                                        danger
                                    >
                                        Clear Cache
                                    </Button>
                                </Col>
                            </Row>
                        </Card>
                    </Col>
                </Row>
            </Card>
        </div>
    );
};

export default Settings;

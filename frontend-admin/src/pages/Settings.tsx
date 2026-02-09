import React, { useState, useEffect } from 'react';
import {
    Card,
    Row,
    Col,
    Switch,
    Select,
    Button,
    Input,
    message,
    Spin,
    Alert,
    Typography,
    Divider,
    Space
} from 'antd';
import { SaveOutlined, ReloadOutlined, ClearOutlined } from '@ant-design/icons';
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
                            <div>
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
                    </Row>
                )}
            </Card>

            {/* Cache Management */}
            <Card title="Cache Management">
                <Paragraph>
                    Clear the configuration cache to reload settings from the database.
                </Paragraph>
                <Button
                    type="default"
                    icon={<ClearOutlined />}
                    onClick={handleClearCache}
                    danger
                >
                    Clear Configuration Cache
                </Button>
            </Card>
        </div>
    );
};

export default Settings;

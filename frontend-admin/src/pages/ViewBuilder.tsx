/**
 * View Builder Page
 * =================
 * Allows admins to create SQL views from raw tables with AI-powered column mapping.
 */
import React, { useState, useEffect } from 'react';
import {
    Layout, Typography, Steps, Form, Select, Input, Button,
    Table, Card, Alert, Space, message
} from 'antd';
import {
    DatabaseOutlined,
    TableOutlined,
    CheckCircleOutlined,
    RobotOutlined
} from '@ant-design/icons';
import { viewBuilderService } from '../services/viewBuilder';
import type { ViewMappingSuggestion } from '../services/viewBuilder';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const ViewBuilder: React.FC = () => {
    const [currentStep, setCurrentStep] = useState(0);
    const [loading, setLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);

    // Data State
    const [tables, setTables] = useState<string[]>([]);
    const [selectedTable, setSelectedTable] = useState<string>('');
    const [viewName, setViewName] = useState<string>('');
    const [mappings, setMappings] = useState<ViewMappingSuggestion[]>([]);

    // Errors
    const [error, setError] = useState<string | null>(null);

    // Fetch Tables on Mount
    useEffect(() => {
        fetchTables();
    }, []);

    const fetchTables = async () => {
        try {
            setLoading(true);
            const data = await viewBuilderService.listTables();
            setTables(data);
        } catch (err: any) {
            setError(err.message || 'Failed to load tables');
        } finally {
            setLoading(false);
        }
    };

    const handleTableSelect = async (table: string) => {
        setSelectedTable(table);
        // Auto-generate view name suggestion
        if (!viewName) {
            setViewName(`v_${table.toLowerCase()}`);
        }
    };

    const fetchSuggestions = async () => {
        if (!selectedTable) return;

        try {
            setAiLoading(true);
            const suggestions = await viewBuilderService.suggestMapping(selectedTable);

            // Transform to editable state if needed, or just use as is
            // We adding a key for Antd Table
            const keyedSuggestions = suggestions.map((s, idx) => ({ ...s, key: idx }));
            setMappings(keyedSuggestions as any);

            next();
        } catch (err: any) {
            message.error('Failed to get AI suggestions: ' + err.message);
        } finally {
            setAiLoading(false);
        }
    };

    const handleMappingChange = (key: number, field: string, value: string) => {
        const newMappings = [...mappings];
        newMappings[key] = { ...newMappings[key], [field]: value };
        setMappings(newMappings);
    };

    const handleCreateView = async () => {
        try {
            setLoading(true);
            await viewBuilderService.createView({
                view_name: viewName,
                source_table: selectedTable,
                mapping: mappings.map(m => ({
                    col: m.col,
                    alias: m.suggested_alias
                }))
            });
            message.success(`View ${viewName} created successfully!`);
            // Reset or Redirect
            setCurrentStep(0);
            setSelectedTable('');
            setViewName('');
            setMappings([]);
        } catch (err: any) {
            message.error(err.response?.data?.detail || 'Failed to create view');
        } finally {
            setLoading(false);
        }
    };

    const next = () => setCurrentStep(currentStep + 1);
    const prev = () => setCurrentStep(currentStep - 1);

    // ==========================================
    // Render Steps
    // ==========================================

    const renderStep1 = () => (
        <Card title="Step 1: Select Source Table" bordered={false}>
            <Form layout="vertical">
                <Form.Item label="Source Table" required>
                    <Select
                        showSearch
                        placeholder="Select a raw table"
                        optionFilterProp="children"
                        loading={loading}
                        onChange={handleTableSelect}
                        value={selectedTable}
                        filterOption={(input, option) =>
                            (option?.children as unknown as string).toLowerCase().includes(input.toLowerCase())
                        }
                    >
                        {tables.map(t => (
                            <Option key={t} value={t}>{t}</Option>
                        ))}
                    </Select>
                </Form.Item>

                <Form.Item label="Target View Name" required help="Standard naming: v_entity_name">
                    <Input
                        prefix="v_"
                        placeholder="sales_2024"
                        value={viewName.replace(/^v_/, '')}
                        onChange={e => setViewName(`v_${e.target.value}`)}
                    />
                </Form.Item>

                <Button
                    type="primary"
                    onClick={fetchSuggestions}
                    disabled={!selectedTable || !viewName}
                    loading={aiLoading}
                    icon={<RobotOutlined />}
                >
                    {aiLoading ? 'Asking AI for Suggestions...' : 'Next: Map Columns with AI'}
                </Button>
            </Form>
        </Card>
    );

    const renderStep2 = () => {
        const columns = [
            {
                title: 'Original Column',
                dataIndex: 'col',
                key: 'col',
                width: '30%',
            },
            {
                title: 'Suggested Alias (Snake Case)',
                dataIndex: 'suggested_alias',
                key: 'suggested_alias',
                render: (text: string, _record: any, index: number) => (
                    <Input
                        value={text}
                        onChange={e => handleMappingChange(index, 'suggested_alias', e.target.value)}
                    />
                )
            },
            {
                title: 'AI Reasoning',
                dataIndex: 'reason',
                key: 'reason',
                width: '30%',
                render: (text: string) => <Text type="secondary" italic>{text}</Text>
            }
        ];

        return (
            <Card title="Step 2: Customize Column Mappings" bordered={false}>
                <Alert
                    message="AI Suggestions Applied"
                    description="Review the suggested aliases below. You can manually edit any alias before creating the view."
                    type="info"
                    showIcon
                    closable
                    style={{ marginBottom: 16 }}
                />

                <Table
                    dataSource={mappings}
                    columns={columns}
                    pagination={false}
                    size="small"
                    scroll={{ y: 400 }}
                />

                <div style={{ marginTop: 24, textAlign: 'right' }}>
                    <Space>
                        <Button onClick={prev}>Back</Button>
                        <Button type="primary" onClick={next}>Next: Review</Button>
                    </Space>
                </div>
            </Card>
        );
    };

    const renderStep3 = () => (
        <Card title="Step 3: Review & Create" bordered={false}>
            <Alert
                message="Ready to Create View"
                description={`This will create a new SQL View named '${viewName}' based on '${selectedTable}' with the defined mappings.`}
                type="success"
                showIcon
                style={{ marginBottom: 24 }}
            />

            <Paragraph>
                <strong>Source:</strong> {selectedTable}<br />
                <strong>Target:</strong> {viewName}<br />
                <strong>Columns:</strong> {mappings.length} mapped columns
            </Paragraph>

            <div style={{ marginTop: 24 }}>
                <Space>
                    <Button onClick={prev}>Back</Button>
                    <Button
                        type="primary"
                        icon={<CheckCircleOutlined />}
                        onClick={handleCreateView}
                        loading={loading}
                    >
                        Create View Now
                    </Button>
                </Space>
            </div>
        </Card>
    );

    const stepItems = [
        { title: 'Select Source', icon: <DatabaseOutlined /> },
        { title: 'Map Columns', icon: <RobotOutlined /> },
        { title: 'Create View', icon: <CheckCircleOutlined /> }
    ];

    return (
        <Layout style={{ padding: '24px', background: '#f0f2f5', minHeight: '100%' }}>
            <Title level={2}><TableOutlined /> View Builder</Title>
            <Paragraph>
                Create simplified SQL Views from raw database tables using AI suggestions.
            </Paragraph>

            {error && (
                <Alert
                    message="Error"
                    description={error}
                    type="error"
                    showIcon
                    closable
                    onClose={() => setError(null)}
                    style={{ marginBottom: 16 }}
                />
            )}

            <Steps
                current={currentStep}
                items={stepItems}
                style={{ marginBottom: 24, maxWidth: 800 }}
            />

            <div style={{ maxWidth: 1000 }}>
                {currentStep === 0 && renderStep1()}
                {currentStep === 1 && renderStep2()}
                {currentStep === 2 && renderStep3()}
            </div>
        </Layout>
    );
};

export default ViewBuilder;

import React, { useState } from 'react';
import { Steps, Upload, Button, Card, Table, Input, Select, Switch, message, Space, Tabs, Descriptions, Tag, Row, Col, Modal, Form } from 'antd';
import { InboxOutlined, LeftOutlined, CheckCircleOutlined, PlusOutlined, DeleteOutlined, EditOutlined, RobotOutlined } from '@ant-design/icons';
import { useMutation } from '@tanstack/react-query';
import { uploadFile, analyzeText, getAISuggestions, importSchema } from '../services/analyzer';
import type { AnalysisRequest, AnalysisResult } from '../services/analyzer';
import type { ColumnsType } from 'antd/es/table';

const { Dragger } = Upload;
const { TextArea } = Input;
const { Option } = Select;

const Analyzer: React.FC = () => {
    const [currentStep, setCurrentStep] = useState(0);
    const [analysisRequest, setAnalysisRequest] = useState<AnalysisRequest | null>(null);
    const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
    const [tableName, setTableName] = useState<string>('');
    const [textInput, setTextInput] = useState('');

    // UI State for Editing
    const [isEditModalVisible, setIsEditModalVisible] = useState(false);
    const [editType, setEditType] = useState<'metadata' | 'mapping' | 'rule'>('metadata');
    const [editData, setEditData] = useState<any>(null);
    const [form] = Form.useForm();

    // Mutations
    const uploadMutation = useMutation({
        mutationFn: uploadFile,
        onSuccess: (data) => {
            setAnalysisRequest(data);
            message.success('File parsed successfully. Ready for AI analysis.');
            // Auto-advance to next logical step
        },
        onError: (error: any) => message.error(`Upload failed: ${error.message}`)
    });

    const aiMutation = useMutation({
        mutationFn: getAISuggestions,
        onSuccess: (data) => {
            setAnalysisResult(data);
            setCurrentStep(1);
            message.success('AI Analysis complete!');
        },
        onError: (error: any) => message.error(`AI Analysis failed: ${error.message}`)
    });

    const importMutation = useMutation({
        mutationFn: importSchema,
        onSuccess: () => {
            setCurrentStep(2);
            message.success('Schema imported successfully!');
        },
        onError: (error: any) => message.error(`Import failed: ${error.message}`)
    });

    const customRequest = async (options: any) => {
        const { file, onSuccess, onError } = options;
        try {
            // Infer table name from filename
            const name = (file as File).name.split('.')[0].replace(/[^a-zA-Z0-9_]/g, '_').toLowerCase();
            setTableName(name);

            await uploadMutation.mutateAsync(file);
            onSuccess("ok");
        } catch (err) {
            onError(err);
        }
    };

    const handleAnalyze = () => {
        if (!analysisRequest) return;
        aiMutation.mutate(analysisRequest);
    };

    const textMutation = useMutation({
        mutationFn: (data: { content: string, table_name: string }) => analyzeText(data.content, data.table_name),
        onSuccess: (data) => {
            setAnalysisRequest(data);
            message.success('Text parsed successfully. Ready for AI analysis.');
        },
        onError: (error: any) => message.error(`Text parsing failed: ${error.message}`)
    });

    const handleTextAnalyze = () => {
        if (!textInput.trim()) {
            message.error("Please enter some CSV data");
            return;
        }
        // Use default table name if not provided
        const targetTable = tableName || 'imported_table';
        if (!tableName) setTableName(targetTable);

        textMutation.mutate({ content: textInput, table_name: targetTable });
    };

    const handleImport = () => {
        if (!analysisResult || !tableName) return;

        importMutation.mutate({
            table_name: tableName,
            metadata: analysisResult.metadata,
            mappings: analysisResult.mappings,
            rules: analysisResult.rules
        });
    };

    // --- Editing Logic ---

    const openEditModal = (type: 'metadata' | 'mapping' | 'rule', data: any = null) => {
        setEditType(type);
        setEditData(data);
        form.resetFields();
        if (data) {
            form.setFieldsValue(data);
        } else {
            // Defaults for new items
            if (type === 'mapping') form.setFieldsValue({ keyword_type: 'term', is_active: true });
            if (type === 'rule') form.setFieldsValue({ severity: 'warning', is_active: true });
        }
        setIsEditModalVisible(true);
    };

    const handleSaveEdit = () => {
        form.validateFields().then(values => {
            if (!analysisResult) return;

            const newData = { ...analysisResult };

            if (editType === 'metadata') {
                // Update existing
                const index = newData.metadata.findIndex(m => m.column_name === editData.column_name);
                if (index !== -1) {
                    newData.metadata[index] = { ...newData.metadata[index], ...values };
                }
            } else if (editType === 'mapping') {
                if (editData) {
                    // Edit
                    const index = newData.mappings.findIndex(m => m.keyword === editData.keyword); // Using keyword as key might be risky if changed, but simple for now
                    // Ideally we track by temporary ID
                    if (index !== -1) newData.mappings[index] = { ...values };
                } else {
                    // Add
                    newData.mappings.push(values);
                }
            } else if (editType === 'rule') {
                if (editData) {
                    const index = newData.rules.findIndex(r => r.rule_code === editData.rule_code);
                    if (index !== -1) newData.rules[index] = { ...values };
                } else {
                    newData.rules.push(values);
                }
            }

            setAnalysisResult(newData);
            setIsEditModalVisible(false);
            message.success('Updates applied to review list');
        });
    };

    const handleDelete = (type: 'mapping' | 'rule', item: any) => {
        if (!analysisResult) return;
        const newData = { ...analysisResult };
        if (type === 'mapping') {
            newData.mappings = newData.mappings.filter(m => m.keyword !== item.keyword);
        } else if (type === 'rule') {
            newData.rules = newData.rules.filter(r => r.rule_code !== item.rule_code);
        }
        setAnalysisResult(newData);
        message.success('Item removed');
    };

    // --- Columns Definitions ---

    const metadataColumns: ColumnsType<any> = [
        { title: 'Column', dataIndex: 'column_name', key: 'column_name', width: 150 },
        { title: 'Type', dataIndex: 'data_type', key: 'data_type', width: 100 },
        { title: 'Thai Name', dataIndex: 'display_name_th', key: 'display_name_th' },
        { title: 'English Name', dataIndex: 'display_name_en', key: 'display_name_en' },
        {
            title: 'Config',
            key: 'config',
            render: (_, r) => <Space>{r.is_summable && <Tag color="green">SUM</Tag>}{r.is_groupable && <Tag color="blue">GROUP</Tag>}</Space>
        },
        {
            title: 'Action',
            key: 'action',
            width: 80,
            render: (_, r) => <Button type="text" icon={<EditOutlined />} onClick={() => openEditModal('metadata', r)} />
        }
    ];

    const mappingColumns: ColumnsType<any> = [
        { title: 'Keyword', dataIndex: 'keyword', key: 'keyword' },
        { title: 'Type', dataIndex: 'keyword_type', key: 'keyword_type', render: (t: string) => <Tag>{t}</Tag> },
        { title: 'Target', dataIndex: 'target_column', key: 'target_column' },
        { title: 'Condition', dataIndex: 'target_condition', key: 'target_condition' },
        {
            title: 'Action',
            key: 'action',
            width: 100,
            render: (_, r) => (
                <Space>
                    <Button type="text" icon={<EditOutlined />} onClick={() => openEditModal('mapping', r)} />
                    <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDelete('mapping', r)} />
                </Space>
            )
        }
    ];

    const ruleColumns: ColumnsType<any> = [
        { title: 'Rule Code', dataIndex: 'rule_code', key: 'rule_code' },
        { title: 'Name', dataIndex: 'rule_name', key: 'rule_name' },
        { title: 'Severity', dataIndex: 'severity', key: 'severity' },
        {
            title: 'Action',
            key: 'action',
            width: 100,
            render: (_, r) => (
                <Space>
                    <Button type="text" icon={<EditOutlined />} onClick={() => openEditModal('rule', r)} />
                    <Button type="text" danger icon={<DeleteOutlined />} onClick={() => handleDelete('rule', r)} />
                </Space>
            )
        }
    ];

    // --- Steps Content ---

    const renderUploadStep = () => (
        <Card title="Step 1: Provide Source Data" style={{ marginTop: 24 }}>
            <Tabs
                defaultActiveKey="file"
                items={[
                    {
                        key: 'file',
                        label: 'File Upload',
                        children: (
                            <>
                                <Dragger
                                    customRequest={customRequest}
                                    showUploadList={false}
                                    multiple={false}
                                    accept=".csv,.xlsx,.xls"
                                    disabled={uploadMutation.isPending}
                                >
                                    <p className="ant-upload-drag-icon">
                                        <InboxOutlined />
                                    </p>
                                    <p className="ant-upload-text">Click or drag file to this area to upload</p>
                                    <p className="ant-upload-hint">
                                        Support for CSV or Excel files. We will parse the file to detect columns.
                                    </p>
                                </Dragger>
                            </>
                        )
                    },
                    {
                        key: 'text',
                        label: 'Free Text (CSV)',
                        children: (
                            <div style={{ padding: 12 }}>
                                <div style={{ marginBottom: 16 }}>
                                    <label>Target Table Name:</label>
                                    <Input
                                        placeholder="e.g. customer_leads"
                                        value={tableName}
                                        onChange={(e) => setTableName(e.target.value)}
                                        style={{ marginTop: 8 }}
                                    />
                                </div>
                                <div style={{ marginBottom: 16 }}>
                                    <label>Paste Data (CSV format):</label>
                                    <TextArea
                                        rows={10}
                                        placeholder="id,name,email&#10;1,John,john@example.com"
                                        value={textInput}
                                        onChange={(e) => setTextInput(e.target.value)}
                                        style={{ marginTop: 8, fontFamily: 'monospace' }}
                                    />
                                </div>
                                <Button
                                    type="primary"
                                    onClick={handleTextAnalyze}
                                    loading={textMutation.isPending}
                                    disabled={!textInput.trim()}
                                >
                                    Parse Text
                                </Button>
                            </div>
                        )
                    }
                ]}
            />

            {analysisRequest && (
                <div style={{ marginTop: 24, padding: 24, background: '#f5f5f5', borderRadius: 8 }}>
                    <h3>Analysis Ready <CheckCircleOutlined style={{ color: 'green' }} /></h3>
                    <p>Detected <strong>{analysisRequest.columns.length}</strong> columns from input.</p>
                    <p>Target Table Name: <strong>{tableName}</strong></p>
                    <Button
                        type="primary"
                        size="large"
                        icon={<RobotOutlined />}
                        onClick={handleAnalyze}
                        loading={aiMutation.isPending}
                    >
                        Start AI Analysis
                    </Button>
                </div>
            )}
        </Card>
    );

    const renderReviewStep = () => (
        <div style={{ marginTop: 24 }}>
            <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={24}>
                    <Card>
                        <Descriptions title="Import Summary">
                            <Descriptions.Item label="Target Table">{tableName}</Descriptions.Item>
                            <Descriptions.Item label="Metadata">{analysisResult?.metadata.length} columns</Descriptions.Item>
                            <Descriptions.Item label="Mappings">{analysisResult?.mappings.length} items</Descriptions.Item>
                            <Descriptions.Item label="Rules">{analysisResult?.rules.length} items</Descriptions.Item>
                        </Descriptions>
                    </Card>
                </Col>
            </Row>

            <Card>
                <Tabs defaultActiveKey="1" items={[
                    {
                        key: '1',
                        label: 'Column Metadata',
                        children: <Table columns={metadataColumns} dataSource={analysisResult?.metadata || []} rowKey="column_name" pagination={false} />
                    },
                    {
                        key: '2',
                        label: 'Semantic Mappings',
                        children: (
                            <>
                                <Button type="dashed" icon={<PlusOutlined />} onClick={() => openEditModal('mapping')} style={{ marginBottom: 16 }}>
                                    Add Custom Mapping
                                </Button>
                                <Table columns={mappingColumns} dataSource={analysisResult?.mappings || []} rowKey="keyword" pagination={false} />
                            </>
                        )
                    },
                    {
                        key: '3',
                        label: 'Business Rules',
                        children: (
                            <>
                                <Button type="dashed" icon={<PlusOutlined />} onClick={() => openEditModal('rule')} style={{ marginBottom: 16 }}>
                                    Add Custom Rule
                                </Button>
                                <Table columns={ruleColumns} dataSource={analysisResult?.rules || []} rowKey="rule_code" pagination={false} />
                            </>
                        )
                    }
                ]} />

                <div style={{ marginTop: 24, display: 'flex', justifyContent: 'space-between' }}>
                    <Button icon={<LeftOutlined />} onClick={() => setCurrentStep(0)}>Back</Button>
                    <Button type="primary" size="large" onClick={handleImport} loading={importMutation.isPending}>
                        Confirm & Import
                    </Button>
                </div>
            </Card>
        </div>
    );

    const renderFinishStep = () => (
        <Card style={{ marginTop: 24, textAlign: 'center', padding: 50 }}>
            <CheckCircleOutlined style={{ fontSize: 72, color: '#52c41a' }} />
            <h2 style={{ marginTop: 24 }}>Import Successful!</h2>
            <p>Schema metadata, mappings, and rules have been imported into the database.</p>
            <div style={{ marginTop: 24 }}>
                <Button key="console" onClick={() => window.location.href = '/schema'}>
                    View Schema
                </Button>
                <Button key="buy" type="primary" onClick={() => window.location.reload()} style={{ marginLeft: 8 }}>
                    Analyze Another File
                </Button>
            </div>
        </Card>
    );

    return (
        <div>
            <h2>Schema Analyzer</h2>
            <Steps
                current={currentStep}
                items={[
                    { title: 'Upload & Parse' },
                    { title: 'Review Suggestions' },
                    { title: 'Import' },
                ]}
            />

            {currentStep === 0 && renderUploadStep()}
            {currentStep === 1 && renderReviewStep()}
            {currentStep === 2 && renderFinishStep()}

            {/* Edit Modal */}
            <Modal
                title={`Edit ${editType === 'metadata' ? 'Column Metadata' : editType === 'mapping' ? 'Mapping' : 'Rule'}`}
                open={isEditModalVisible}
                onOk={handleSaveEdit}
                onCancel={() => setIsEditModalVisible(false)}
                width={700}
            >
                <Form form={form} layout="vertical">
                    {editType === 'metadata' && (
                        <>
                            <Form.Item name="display_name_th" label="Thai Name"><Input /></Form.Item>
                            <Form.Item name="display_name_en" label="English Name"><Input /></Form.Item>
                            <Form.Item name="description" label="Description"><TextArea /></Form.Item>
                            <Space>
                                <Form.Item name="is_summable" label="Summable" valuePropName="checked"><Switch /></Form.Item>
                                <Form.Item name="is_groupable" label="Groupable" valuePropName="checked"><Switch /></Form.Item>
                            </Space>
                        </>
                    )}
                    {editType === 'mapping' && (
                        <>
                            <Form.Item name="keyword" label="Keyword" rules={[{ required: true }]}><Input /></Form.Item>
                            <Form.Item name="keyword_type" label="Type"><Select><Option value="term">Term</Option><Option value="abbreviation">Abbreviation</Option><Option value="synonym">Synonym</Option></Select></Form.Item>
                            <Form.Item name="target_column" label="Target Column" rules={[{ required: true }]}><Input /></Form.Item>
                            <Form.Item name="target_condition" label="Condition" rules={[{ required: true }]}><Input /></Form.Item>
                            <Form.Item name="description" label="Description"><TextArea /></Form.Item>
                        </>
                    )}
                    {editType === 'rule' && (
                        <>
                            <Form.Item name="rule_code" label="Code" rules={[{ required: true }]}><Input /></Form.Item>
                            <Form.Item name="rule_name" label="Name" rules={[{ required: true }]}><Input /></Form.Item>
                            <Form.Item name="rule_description" label="Description"><TextArea /></Form.Item>
                            <Form.Item name="example_correct" label="Correct SQL"><TextArea style={{ fontFamily: 'monospace' }} /></Form.Item>
                            <Form.Item name="example_wrong" label="Wrong SQL"><TextArea style={{ fontFamily: 'monospace' }} /></Form.Item>
                            <Form.Item name="severity" label="Severity"><Select><Option value="warning">Warning</Option><Option value="error">Error</Option></Select></Form.Item>
                        </>
                    )}
                </Form>
            </Modal>
        </div>
    );
};

export default Analyzer;

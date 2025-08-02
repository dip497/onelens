import React, { useState, useEffect } from 'react';
import { FileText, Link2, Search, MessageSquare, Target } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import api from '@/services/api';

interface RFPDocument {
  id: string;
  filename: string;
  customer_id?: string;
  processed_status: string;
  total_questions?: number;
  processed_questions?: number;
  business_context?: any;
  created_at: string;
  updated_at: string;
}

interface QAPair {
  id: string;
  question: string;
  answer: string;
  feature_id?: string;
  customer_context?: any;
  business_impact_estimate?: number;
  feature?: {
    id: string;
    title: string;
    description: string;
  };
}

interface RFPDetailDialogProps {
  document: RFPDocument;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function RFPDetailDialog({
  document,
  open,
  onOpenChange,
}: RFPDetailDialogProps) {
  const [qaPairs, setQAPairs] = useState<QAPair[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [generatedResponses, setGeneratedResponses] = useState<any[]>([]);
  const [generatingResponses, setGeneratingResponses] = useState(false);

  // Get purpose from document's business context
  const purpose = document.business_context?.purpose || 'analyze';

  useEffect(() => {
    if (open && document) {
      fetchQAPairs();
    }
  }, [open, document]);

  const fetchQAPairs = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/rfp/${document.id}/qa-pairs`);
      setQAPairs(response.data);
    } catch (error) {
      console.error('Failed to fetch Q&A pairs:', error);
    } finally {
      setLoading(false);
    }
  };

  const generateResponses = async () => {
    try {
      setGeneratingResponses(true);
      const response = await api.post(`/rfp/${document.id}/generate-responses`);
      setGeneratedResponses(response.data.responses || []);
    } catch (error) {
      console.error('Failed to generate responses:', error);
    } finally {
      setGeneratingResponses(false);
    }
  };

  const filteredQAPairs = qaPairs.filter((qa) => {
    const searchLower = searchQuery.toLowerCase();
    return (
      qa.question.toLowerCase().includes(searchLower) ||
      qa.answer.toLowerCase().includes(searchLower)
    );
  });

  const linkedFeatures = qaPairs.filter((qa) => qa.feature_id).length;
  const unlinkedQuestions = qaPairs.filter((qa) => !qa.feature_id).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[80vh]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            {document.filename}
          </DialogTitle>
          <DialogDescription>
            Processed {document.processed_questions || 0} of{' '}
            {document.total_questions || 0} questions
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue={purpose === 'respond' ? 'questions' : 'review'} className="w-full">
          {purpose === 'respond' ? (
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="questions">Questions</TabsTrigger>
              <TabsTrigger value="responses">AI Responses</TabsTrigger>
            </TabsList>
          ) : (
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="review">Review & Verify</TabsTrigger>
              <TabsTrigger value="analysis">Feature Analysis</TabsTrigger>
            </TabsList>
          )}

          {/* Questions tab for respond mode */}
          {purpose === 'respond' && (
            <TabsContent value="questions" className="space-y-4">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="text-lg font-semibold">RFP Questions</h3>
                  <p className="text-sm text-muted-foreground">
                    Questions that need professional responses
                  </p>
                </div>
                <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                  {qaPairs.length} Questions
                </Badge>
              </div>

              <ScrollArea className="h-[400px] pr-4">
                <div className="space-y-4">
                  {qaPairs.map((qa, index) => (
                    <Card key={qa.id}>
                      <CardHeader className="pb-3">
                        <CardTitle className="text-base flex items-center gap-2">
                          <MessageSquare className="h-4 w-4 text-primary" />
                          <span className="text-xs text-muted-foreground mr-2">Q{index + 1}:</span>
                          {qa.question}
                        </CardTitle>
                      </CardHeader>
                    </Card>
                  ))}
                </div>
              </ScrollArea>
            </TabsContent>
          )}

          {/* AI Responses tab for respond mode */}
          {purpose === 'respond' && (
            <TabsContent value="responses" className="space-y-4">
              <div className="flex justify-between items-center">
                <div>
                  <h3 className="text-lg font-semibold">AI Response Generator</h3>
                  <p className="text-sm text-muted-foreground">
                    Generate professional RFP responses using your company's knowledge base
                  </p>
                </div>
                <Button
                  onClick={generateResponses}
                  disabled={generatingResponses || qaPairs.length === 0}
                  className="bg-primary hover:bg-primary/90"
                >
                  {generatingResponses ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></div>
                      Generating...
                    </>
                  ) : (
                    'Generate Responses'
                  )}
                </Button>
              </div>

              {generatedResponses.length > 0 ? (
                <ScrollArea className="h-[400px] pr-4">
                  <div className="space-y-4">
                    {generatedResponses.map((response, index) => (
                      <Card key={index}>
                        <CardHeader className="pb-3">
                          <div className="flex justify-between items-start">
                            <CardTitle className="text-base">
                              Q: {response.question}
                            </CardTitle>
                            <Badge
                              variant={
                                response.confidence === 'High' ? 'success' :
                                response.confidence === 'Medium' ? 'secondary' : 'outline'
                              }
                            >
                              {response.confidence} Confidence
                            </Badge>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-3">
                            <div>
                              <h4 className="font-medium text-sm mb-2">Suggested Answer:</h4>
                              <p className="text-sm bg-muted/50 rounded-md p-3">
                                {response.suggested_answer}
                              </p>
                            </div>
                            {response.sources_used && response.sources_used.length > 0 && (
                              <div>
                                <h4 className="font-medium text-sm mb-2">Sources Used:</h4>
                                <div className="flex flex-wrap gap-1">
                                  {response.sources_used.map((source: string, idx: number) => (
                                    <Badge key={idx} variant="outline" className="text-xs">
                                      {source}
                                    </Badge>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                </ScrollArea>
              ) : (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-8">
                    <div className="text-center">
                      <h4 className="font-medium mb-2">No responses generated yet</h4>
                      <p className="text-sm text-muted-foreground mb-4">
                        Click "Generate Responses" to create professional RFP responses using your knowledge base
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          )}

          {/* Review tab for analyze mode */}
          {purpose === 'analyze' && (
            <>
              <TabsContent value="review" className="space-y-4">
            <div className="flex justify-between items-center">
              <div>
                <h3 className="text-lg font-semibold">Review & Verify</h3>
                <p className="text-sm text-muted-foreground">
                  Review extracted Q&A pairs and verify accuracy before generating responses
                </p>
              </div>
              <div className="flex items-center gap-4">
                <div className="relative">
                  <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search questions or answers..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-8 w-[300px]"
                  />
                </div>
                <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-200">
                  {qaPairs.length} Q&A Pairs
                </Badge>
              </div>
            </div>

            <ScrollArea className="h-[400px] pr-4">
              <div className="space-y-4">
                {filteredQAPairs.map((qa, index) => (
                  <Card key={qa.id}>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-base flex items-center gap-2">
                        <MessageSquare className="h-4 w-4 text-primary" />
                        <span className="text-xs text-muted-foreground mr-2">Q{index + 1}:</span>
                        {qa.question}
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="bg-gray-50 rounded-md p-3">
                        <h4 className="font-medium text-sm mb-2">Original Answer:</h4>
                        <p className="text-sm text-muted-foreground">
                          {qa.answer || "No answer provided in the original RFP"}
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </ScrollArea>
          </TabsContent>

              <TabsContent value="analysis" className="space-y-4">
                <div className="flex justify-between items-center">
                  <div>
                    <h3 className="text-lg font-semibold">Feature Analysis</h3>
                    <p className="text-sm text-muted-foreground">
                      Features identified and linked from this RFP document
                    </p>
                  </div>
                  <Badge variant="outline" className="bg-green-50 text-green-700 border-green-200">
                    {qaPairs.filter((qa) => qa.feature).length} Linked Features
                  </Badge>
                </div>

                <ScrollArea className="h-[400px] pr-4">
                  <div className="space-y-4">
                    {qaPairs
                      .filter((qa) => qa.feature)
                      .map((qa) => (
                        <Card key={qa.id}>
                          <CardHeader className="pb-3">
                            <CardTitle className="text-base flex items-center gap-2">
                              <Target className="h-4 w-4 text-primary" />
                              {qa.feature!.title}
                            </CardTitle>
                          </CardHeader>
                          <CardContent>
                            <div className="space-y-3">
                              <p className="text-sm text-muted-foreground">
                                {qa.feature!.description}
                              </p>
                              <div className="bg-muted/50 rounded-md p-3">
                                <h4 className="font-medium text-sm mb-2">Referenced Question:</h4>
                                <p className="text-sm text-muted-foreground">
                                  {qa.question}
                                </p>
                              </div>
                            </div>
                          </CardContent>
                        </Card>
                      ))}
                    {qaPairs.filter((qa) => qa.feature).length === 0 && (
                      <Card>
                        <CardContent className="flex flex-col items-center justify-center py-8">
                          <div className="text-center">
                            <h4 className="font-medium mb-2">No features linked yet</h4>
                            <p className="text-sm text-muted-foreground">
                              Features will be automatically linked during processing
                            </p>
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                </ScrollArea>
              </TabsContent>
            </>
          )}
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
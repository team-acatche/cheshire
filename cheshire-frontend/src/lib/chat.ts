export interface ResponseMessages {
    messages: ResponseMessage[];
}

export interface ResponseMessage {
    _role: string;
    _content: ResponseMessageContent[];
}

export interface ResponseMessageContent {
    text: string;
}
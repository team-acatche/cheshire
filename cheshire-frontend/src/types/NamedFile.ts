import { v4 as uuidv4 } from "uuid";

export class NamedFile {
    name: string;
    contents: File | Blob;

    constructor(f: File);
    constructor(content: File | Blob, name: string);
    constructor(content: File | Blob, name?: string) {
        this.name = name ?? ((content instanceof File) ? content.name : uuidv4());
        this.contents = content;
    }
}
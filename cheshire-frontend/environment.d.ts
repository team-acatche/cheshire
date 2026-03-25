declare namespace NodeJS {
    interface ProcessEnv {
        BACKEND_URI: string;
        NODE_ENV: "production" | "development";
        PORT?: string;
        PWD: string;
    }
}

export {}